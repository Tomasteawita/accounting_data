"""
Vistas de la aplicación app.
Incluye la Landing Page, el módulo de Autenticación, el Dashboard y el módulo de Transacciones
con ingesta masiva en memoria mediante pandas.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import gc
import io
import json
import os
import unicodedata

import pandas as pd
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_http_methods

from .forms import (
    ClienteForm,
    CustomAuthenticationForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    CustomUserCreationForm,
    ResendActivationForm,
    TransactionBulkUploadForm,
    TransactionForm,
)
from .models import Client, Cliente, Transaction
from .utils import send_activation_email

CustomUser = get_user_model()

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
ALLOWED_PAGE_SIZES = (25, 50, 100)

NON_OPERATING_EXPENSE_CONCEPTS = {"deuda", "estructura"}

MONTH_HEADERS = [
    (1, "Ene"),
    (2, "Feb"),
    (3, "Mar"),
    (4, "Abr"),
    (5, "May"),
    (6, "Jun"),
    (7, "Jul"),
    (8, "Ago"),
    (9, "Sep"),
    (10, "Oct"),
    (11, "Nov"),
    (12, "Dic"),
]


def _normalize_concept_name(raw_concept):
    """
    Normaliza el nombre de un concepto contable eliminando tildes,
    convirtiendo a minúsculas y colapsando espacios múltiples.
    """
    text = str(raw_concept or "").strip().lower()
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return " ".join(text.split())


def _quantize_money(value):
    """Redondea montos monetarios con precisión Decimal(0.01)."""
    return Decimal(value or "0.00").quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _calculate_percentage(numerator, denominator):
    """
    Calcula el porcentaje contable ((numerador / denominador) * 100) con Decimal.
    Si los ingresos (denominador) son 0, devuelve Decimal('0.0') sin lanzar ZeroDivisionError.
    """
    num = Decimal(numerator or "0.00")
    den = Decimal(denominator or "0.00")
    if den == Decimal("0.00"):
        return Decimal("0.0")
    return ((num / den) * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def _finalize_pnl_concept_rows(concept_map, total_income_annual):
    """
    Construye y ordena las filas de un bloque del P&L de mayor a menor monto anual acumulado.
    """
    rows = []
    for item in concept_map.values():
        annual_total = _quantize_money(
            sum(item["monthly"], Decimal("0.00"))
        )
        vertical_pct = _calculate_percentage(annual_total, total_income_annual)
        rows.append(
            {
                "concept": item["concept"],
                "normalized_concept": item["normalized_concept"],
                "monthly": item["monthly"],
                "annual_total": annual_total,
                "vertical_pct": vertical_pct,
                "vertical_pct_display": f"{vertical_pct:.1f}%",
            }
        )
    rows.sort(key=lambda r: (-r["annual_total"], r["concept"].lower()))
    return rows


def _build_pnl_matrix(monthly_aggregates):
    """
    Transforma los agregados mensuales de PostgreSQL en la estructura matricial
    de Estado de Resultados (P&L) de 5 escalones utilizando exclusivamente Decimal.
    """
    income_map = {}
    opex_map = {}
    non_op_map = {}

    for row in monthly_aggregates:
        tx_type = row.get("transaction_type")
        raw_concept = str(row.get("concept") or "Sin concepto").strip() or "Sin concepto"
        norm_concept = _normalize_concept_name(raw_concept)
        month_num = int(row.get("month") or 0)
        if month_num < 1 or month_num > 12:
            continue
        month_idx = month_num - 1
        amount = _quantize_money(row.get("total_amount") or Decimal("0.00"))

        if tx_type == Transaction.TransactionType.INCOME:
            target_map = income_map
        else:
            if norm_concept in NON_OPERATING_EXPENSE_CONCEPTS:
                target_map = non_op_map
            else:
                target_map = opex_map

        if norm_concept not in target_map:
            target_map[norm_concept] = {
                "concept": raw_concept,
                "normalized_concept": norm_concept,
                "monthly": [Decimal("0.00") for _ in range(12)],
            }
        target_map[norm_concept]["monthly"][month_idx] = _quantize_money(
            target_map[norm_concept]["monthly"][month_idx] + amount
        )

    # 1. Ingresos Operativos
    total_income_monthly = [
        _quantize_money(
            sum((item["monthly"][m] for item in income_map.values()), Decimal("0.00"))
        )
        for m in range(12)
    ]
    total_income_annual = _quantize_money(
        sum(total_income_monthly, Decimal("0.00"))
    )
    income_rows = _finalize_pnl_concept_rows(income_map, total_income_annual)
    total_income_pct = _calculate_percentage(total_income_annual, total_income_annual)
    total_income_row = {
        "label": "TOTAL INGRESOS",
        "monthly": total_income_monthly,
        "annual_total": total_income_annual,
        "vertical_pct": total_income_pct,
        "vertical_pct_display": f"{total_income_pct:.1f}%",
    }

    # 2. Gastos Operativos (OPEX)
    opex_rows = _finalize_pnl_concept_rows(opex_map, total_income_annual)
    total_opex_monthly = [
        _quantize_money(
            sum((r["monthly"][m] for r in opex_rows), Decimal("0.00"))
        )
        for m in range(12)
    ]
    total_opex_annual = _quantize_money(
        sum(total_opex_monthly, Decimal("0.00"))
    )
    total_opex_pct = _calculate_percentage(total_opex_annual, total_income_annual)
    total_opex_row = {
        "label": "TOTAL GASTOS OPERATIVOS (OPEX)",
        "monthly": total_opex_monthly,
        "annual_total": total_opex_annual,
        "vertical_pct": total_opex_pct,
        "vertical_pct_display": f"{total_opex_pct:.1f}%",
    }

    # 3. Subtotal 1 — Resultado Operativo (EBITDA) y Margen Operativo (EBITDA %)
    ebitda_monthly = [
        _quantize_money(total_income_monthly[m] - total_opex_monthly[m])
        for m in range(12)
    ]
    ebitda_annual = _quantize_money(total_income_annual - total_opex_annual)
    ebitda_pct = _calculate_percentage(ebitda_annual, total_income_annual)
    ebitda_row = {
        "label": "SUBTOTAL 1 — RESULTADO OPERATIVO (EBITDA)",
        "monthly": ebitda_monthly,
        "annual_total": ebitda_annual,
        "vertical_pct": ebitda_pct,
        "vertical_pct_display": f"{ebitda_pct:.1f}%",
    }

    ebitda_margin_monthly = [
        _calculate_percentage(ebitda_monthly[m], total_income_monthly[m])
        for m in range(12)
    ]
    ebitda_margin_row = {
        "label": "MARGEN OPERATIVO (EBITDA %)",
        "monthly": ebitda_margin_monthly,
        "monthly_display": [f"{pct:.1f}%" for pct in ebitda_margin_monthly],
        "annual_total": ebitda_pct,
        "annual_display": f"{ebitda_pct:.1f}%",
        "vertical_pct": ebitda_pct,
        "vertical_pct_display": f"{ebitda_pct:.1f}%",
    }

    # 4. CAPEX y Servicio de Deuda (No Operativo)
    non_operating_rows = _finalize_pnl_concept_rows(non_op_map, total_income_annual)
    total_non_op_monthly = [
        _quantize_money(
            sum((r["monthly"][m] for r in non_operating_rows), Decimal("0.00"))
        )
        for m in range(12)
    ]
    total_non_op_annual = _quantize_money(
        sum(total_non_op_monthly, Decimal("0.00"))
    )
    total_non_op_pct = _calculate_percentage(total_non_op_annual, total_income_annual)
    total_non_operating_row = {
        "label": "TOTAL NO OPERATIVO (CAPEX + DEUDA)",
        "monthly": total_non_op_monthly,
        "annual_total": total_non_op_annual,
        "vertical_pct": total_non_op_pct,
        "vertical_pct_display": f"{total_non_op_pct:.1f}%",
    }

    # 5. Resultado Neto de Caja (Flujo Libre) y Margen Neto (%)
    net_result_monthly = [
        _quantize_money(ebitda_monthly[m] - total_non_op_monthly[m])
        for m in range(12)
    ]
    net_result_annual = _quantize_money(ebitda_annual - total_non_op_annual)
    net_result_pct = _calculate_percentage(net_result_annual, total_income_annual)
    net_result_row = {
        "label": "RESULTADO NETO DE CAJA (FLUJO LIBRE)",
        "monthly": net_result_monthly,
        "annual_total": net_result_annual,
        "vertical_pct": net_result_pct,
        "vertical_pct_display": f"{net_result_pct:.1f}%",
    }

    net_margin_monthly = [
        _calculate_percentage(net_result_monthly[m], total_income_monthly[m])
        for m in range(12)
    ]
    net_margin_row = {
        "label": "MARGEN NETO (%)",
        "monthly": net_margin_monthly,
        "monthly_display": [f"{pct:.1f}%" for pct in net_margin_monthly],
        "annual_total": net_result_pct,
        "annual_display": f"{net_result_pct:.1f}%",
        "vertical_pct": net_result_pct,
        "vertical_pct_display": f"{net_result_pct:.1f}%",
    }

    has_transactions = bool(income_rows or opex_rows or non_operating_rows)

    return {
        "income_rows": income_rows,
        "total_income": total_income_row,
        "opex_rows": opex_rows,
        "total_opex": total_opex_row,
        "ebitda": ebitda_row,
        "ebitda_margin": ebitda_margin_row,
        "non_operating_rows": non_operating_rows,
        "total_non_operating": total_non_operating_row,
        "net_result": net_result_row,
        "net_income": net_result_row,
        "net_margin": net_margin_row,
        "has_transactions": has_transactions,
    }


def _parse_pagination_params(source_dict, fallback_dict=None):
    """
    Extrae y valida `page` y `per_page` (por defecto 25, máximo estricto 100).
    """
    fallback_dict = fallback_dict or {}
    raw_per_page = source_dict.get("per_page") or fallback_dict.get("per_page") or DEFAULT_PAGE_SIZE
    raw_page = source_dict.get("page") or fallback_dict.get("page") or 1

    try:
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        per_page = DEFAULT_PAGE_SIZE
    per_page = max(1, min(per_page, MAX_PAGE_SIZE))

    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    return page, per_page


def home(request):
    """
    Si el usuario tiene una sesión iniciada y activa, redirige al Dashboard.
    Para usuarios anónimos, renderiza la Landing Page (app/home.html) sin consultas a PostgreSQL.
    """
    if request.user.is_authenticated:
        return redirect("app:dashboard")
    return render(request, "app/home.html")


@login_required
@require_http_methods(["GET"])
def dashboard_view(request):
    """
    Módulo de Estado de Resultados (P&L Mensual) en la vista de Inicio.
    Realiza la agregación directamente en PostgreSQL con ExtractMonth y Sum('amount')
    sin instanciar DataFrames de pandas para proteger la RAM de la instancia EC2 t4g.small.
    """
    user_tx_qs = Transaction.objects.filter(user=request.user)

    raw_years = list(
        user_tx_qs.annotate(year=ExtractYear("date"))
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )
    available_years = sorted({int(y) for y in raw_years if y is not None}, reverse=True)
    current_year = datetime.now().year
    if not available_years:
        available_years = [current_year]

    raw_verticals = list(
        user_tx_qs.exclude(vertical="")
        .values_list("vertical", flat=True)
        .distinct()
        .order_by("vertical")
    )
    available_verticals = [v for v in raw_verticals if v]

    raw_year_param = (request.GET.get("year") or "").strip()
    try:
        selected_year = int(raw_year_param)
        if selected_year < 1900 or selected_year > 2100:
            raise ValueError
    except ValueError:
        selected_year = available_years[0]

    if selected_year not in available_years:
        available_years = sorted(set(available_years + [selected_year]), reverse=True)

    raw_currency_param = (
        request.GET.get("currency") or Transaction.Currency.ARS
    ).strip().upper()
    valid_currencies = {Transaction.Currency.ARS, Transaction.Currency.USD}
    selected_currency = (
        raw_currency_param
        if raw_currency_param in valid_currencies
        else Transaction.Currency.ARS
    )

    raw_vertical_param = (request.GET.get("vertical") or "").strip()
    if raw_vertical_param.upper() in ("", "TODAS", "ALL"):
        selected_vertical = ""
    else:
        selected_vertical = raw_vertical_param

    pnl_qs = user_tx_qs.filter(
        date__year=selected_year,
        currency=selected_currency,
    )
    if selected_vertical:
        pnl_qs = pnl_qs.filter(vertical=selected_vertical)

    monthly_aggregates = (
        pnl_qs.annotate(month=ExtractMonth("date"))
        .values("transaction_type", "concept", "month")
        .annotate(total_amount=Sum("amount"))
        .order_by("transaction_type", "concept", "month")
    )

    pnl = _build_pnl_matrix(monthly_aggregates)

    kpis = {
        "total_income": pnl["total_income"]["annual_total"],
        "total_opex": pnl["total_opex"]["annual_total"],
        "opex_pct": pnl["total_opex"]["vertical_pct"],
        "ebitda": pnl["ebitda"]["annual_total"],
        "ebitda_margin": pnl["ebitda"]["vertical_pct"],
        "total_non_operating": pnl["total_non_operating"]["annual_total"],
        "net_result": pnl["net_result"]["annual_total"],
        "net_margin": pnl["net_result"]["vertical_pct"],
    }

    context = {
        "selected_year": selected_year,
        "selected_currency": selected_currency,
        "selected_vertical": selected_vertical,
        "available_years": available_years,
        "available_verticals": available_verticals,
        "currencies": [
            (Transaction.Currency.ARS, "ARS"),
            (Transaction.Currency.USD, "USD"),
        ],
        "month_headers": [label for _, label in MONTH_HEADERS],
        "months": [{"num": num, "label": label} for num, label in MONTH_HEADERS],
        "pnl": pnl,
        "kpis": kpis,
        "income_rows": pnl["income_rows"],
        "total_income_row": pnl["total_income"],
        "opex_rows": pnl["opex_rows"],
        "total_opex_row": pnl["total_opex"],
        "ebitda_row": pnl["ebitda"],
        "ebitda_margin_row": pnl["ebitda_margin"],
        "non_operating_rows": pnl["non_operating_rows"],
        "total_non_operating_row": pnl["total_non_operating"],
        "net_result_row": pnl["net_result"],
        "net_margin_row": pnl["net_margin"],
    }
    return render(request, "app/dashboard.html", context)


def _serialize_cliente(c):
    """Serializa una instancia de Cliente incluyendo estado y URL de su documentación PDF."""
    has_pdf = bool(c.documentacion and getattr(c.documentacion, "name", ""))
    pdf_url = ""
    pdf_name = ""
    if has_pdf:
        try:
            pdf_url = c.documentacion.url
            pdf_name = os.path.basename(c.documentacion.name)
        except ValueError:
            has_pdf = False

    return {
        "id": c.id,
        "name": c.nombre_completo,
        "nombre_completo": c.nombre_completo,
        "email": c.email or "",
        "telefono": c.telefono or "",
        "sexo": c.sexo or Cliente.Sexo.OTRO,
        "sexo_display": c.get_sexo_display(),
        "has_pdf": has_pdf,
        "pdf_url": pdf_url,
        "pdf_name": pdf_name,
    }


def _paginate_user_clientes(user, page=1, per_page=DEFAULT_PAGE_SIZE):
    """
    Ejecuta la paginación en base de datos para los clientes del usuario
    y devuelve (page_obj, pagination_meta_dict).
    """
    per_page = max(1, min(int(per_page), MAX_PAGE_SIZE))
    qs = Cliente.objects.filter(user=user).order_by("nombre_completo", "-id")
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    pagination_meta = {
        "page": page_obj.number,
        "per_page": per_page,
        "total_pages": paginator.num_pages,
        "total_count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page": (
            page_obj.previous_page_number() if page_obj.has_previous() else None
        ),
        "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
        "start_index": page_obj.start_index() if paginator.count > 0 else 0,
        "end_index": page_obj.end_index() if paginator.count > 0 else 0,
    }
    return page_obj, pagination_meta


@login_required
@require_http_methods(["GET", "POST"])
def clients_view(request):
    """
    Lista los clientes del usuario y procesa peticiones POST (crear, editar,
    subir PDF individual o eliminar clientes) validando extensión .pdf y límite de 10 MB.
    """
    if request.method == "GET":
        page, per_page = _parse_pagination_params(request.GET)
        page_obj, pagination_meta = _paginate_user_clientes(
            request.user, page=page, per_page=per_page
        )
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )
        if is_ajax:
            return JsonResponse(
                {
                    "status": "ok",
                    "clientes": [
                        _serialize_cliente(c) for c in page_obj.object_list
                    ],
                    "pagination": pagination_meta,
                }
            )

        form = ClienteForm(user=request.user)
        return render(
            request,
            "app/clientes.html",
            {
                "clientes": page_obj.object_list,
                "page_obj": page_obj,
                "pagination": pagination_meta,
                "per_page": per_page,
                "allowed_page_sizes": ALLOWED_PAGE_SIZES,
                "form": form,
            },
        )

    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Formato JSON inválido."}, status=400
            )
    else:
        payload = request.POST.dict()

    page, per_page = _parse_pagination_params(payload, request.GET)
    action = payload.get("action") or "create"

    # 1. Eliminación de cliente
    if action == "delete":
        client_id = payload.get("id")
        if not client_id:
            return JsonResponse(
                {"status": "error", "message": "ID de cliente requerido."},
                status=400,
            )
        cliente = get_object_or_404(Cliente, pk=client_id, user=request.user)
        deleted_id = cliente.id
        if cliente.documentacion:
            cliente.documentacion.delete(save=False)
        cliente.delete()

        page_obj, pagination_meta = _paginate_user_clientes(
            request.user, page=page, per_page=per_page
        )
        return JsonResponse(
            {
                "status": "ok",
                "message": "Cliente eliminado correctamente.",
                "deleted_id": deleted_id,
                "clientes": [_serialize_cliente(c) for c in page_obj.object_list],
                "pagination": pagination_meta,
            }
        )

    # 2. Subida rápida de PDF desde la fila ("Subir PDF")
    if action == "upload_pdf":
        client_id = payload.get("id")
        if not client_id:
            return JsonResponse(
                {"status": "error", "message": "ID de cliente requerido."},
                status=400,
            )
        cliente = get_object_or_404(Cliente, pk=client_id, user=request.user)
        if "documentacion" not in request.FILES:
            return JsonResponse(
                {"status": "error", "message": "Debe adjuntar un archivo PDF válido."},
                status=400,
            )
        data = {
            "nombre_completo": cliente.nombre_completo,
            "email": cliente.email,
            "telefono": cliente.telefono,
            "sexo": cliente.sexo,
        }
        form = ClienteForm(
            data=data,
            files=request.FILES,
            instance=cliente,
            user=request.user,
        )
        if form.is_valid():
            updated_client = form.save()
            return JsonResponse(
                {
                    "status": "ok",
                    "message": "Documentación PDF subida correctamente.",
                    "cliente": _serialize_cliente(updated_client),
                }
            )
        err_msg = "; ".join(
            f"{ errs[0] }" for errs in form.errors.values() if errs
        )
        return JsonResponse(
            {"status": "error", "message": err_msg, "errors": form.errors},
            status=400,
        )

    # 3. Creación o edición de cliente (ClienteForm)
    instance = None
    if action == "update" or payload.get("id"):
        client_id = payload.get("id")
        if client_id:
            instance = get_object_or_404(Cliente, pk=client_id, user=request.user)

    form = ClienteForm(
        data=payload,
        files=request.FILES if request.FILES else None,
        instance=instance,
        user=request.user,
    )
    if form.is_valid():
        cliente_obj = form.save()
        status_code = 200 if instance else 201
        page_obj, pagination_meta = _paginate_user_clientes(
            request.user, page=page, per_page=per_page
        )
        return JsonResponse(
            {
                "status": "ok",
                "message": (
                    "Cliente actualizado correctamente."
                    if instance
                    else "Cliente creado correctamente."
                ),
                "cliente": _serialize_cliente(cliente_obj),
                "clientes": [_serialize_cliente(c) for c in page_obj.object_list],
                "pagination": pagination_meta,
            },
            status=status_code,
        )

    error_summary = "; ".join(
        f"{', '.join(errs)}" for _, errs in form.errors.items()
    )
    return JsonResponse(
        {
            "status": "error",
            "message": error_summary or "Error de validación en los datos del cliente.",
            "errors": form.errors,
        },
        status=400,
    )


@login_required
@require_http_methods(["POST"])
def client_create_view(request):
    """Endpoint dedicado para crear un cliente."""
    return clients_view(request)


@login_required
@require_http_methods(["POST"])
def client_update_view(request, pk):
    """Endpoint dedicado para editar un cliente existente por su PK."""
    cliente = get_object_or_404(Cliente, pk=pk, user=request.user)
    data = request.POST.dict() if request.POST else {}
    if not data and request.content_type and "application/json" in request.content_type:
        data = json.loads(request.body.decode("utf-8") or "{}")
    if "nombre_completo" not in data:
        data["nombre_completo"] = cliente.nombre_completo
    form = ClienteForm(
        data=data,
        files=request.FILES if request.FILES else None,
        instance=cliente,
        user=request.user,
    )
    if form.is_valid():
        updated = form.save()
        return JsonResponse(
            {
                "status": "ok",
                "message": "Cliente actualizado correctamente.",
                "cliente": _serialize_cliente(updated),
            }
        )
    error_summary = "; ".join(
        f"{', '.join(errs)}" for _, errs in form.errors.items()
    )
    return JsonResponse(
        {"status": "error", "message": error_summary, "errors": form.errors},
        status=400,
    )


@login_required
@require_http_methods(["POST"])
def client_delete_view(request, pk):
    """Endpoint dedicado para eliminar un cliente existente por su PK."""
    cliente = get_object_or_404(Cliente, pk=pk, user=request.user)
    deleted_id = cliente.id
    if cliente.documentacion:
        cliente.documentacion.delete(save=False)
    cliente.delete()
    return JsonResponse(
        {
            "status": "ok",
            "message": "Cliente eliminado correctamente.",
            "deleted_id": deleted_id,
        }
    )


def _serialize_transaction(tx):
    """Serializa una instancia de Transaction con los 8 campos operativos."""
    return {
        "id": tx.id,
        "date": tx.date.strftime("%Y-%m-%d") if hasattr(tx.date, "strftime") else str(tx.date),
        "vertical": tx.vertical or "",
        "transaction_type": tx.transaction_type,
        "transaction_type_display": tx.get_transaction_type_display(),
        "concept": tx.concept,
        "client": tx.client_id or "",
        "client_name": tx.client.name if tx.client_id and tx.client else "",
        "detail": tx.detail or "",
        "amount": f"{Decimal(tx.amount):.2f}",
        "currency": tx.currency or Transaction.Currency.ARS,
    }


def _normalize_header(col_name):
    """Normaliza encabezados de columnas eliminando tildes, espacios y mayúsculas."""
    text = str(col_name or "").strip().lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    return text.replace(" ", "_")


def _parse_date_value(raw_val):
    """Convierte cadenas de fecha (priorizando YYYY-MM-DD) a objetos date."""
    val = str(raw_val or "").strip()
    if not val or val.lower() in ("nan", "nat", "none"):
        raise ValueError("Fecha vacía.")
    val_short = val.split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_short, fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(val, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Fecha inválida: '{raw_val}' (use YYYY-MM-DD).")
    return parsed.date()


def _parse_type_value(raw_val):
    """Normaliza el tipo de operación a INGRESO o GASTO."""
    val = _normalize_header(raw_val).upper()
    if val in ("INGRESO", "INGRESOS", "I", "INCOME", "ENTRADA", "COBRO", "+"):
        return Transaction.TransactionType.INCOME
    if val in ("GASTO", "GASTOS", "EGRESO", "EGRESOS", "E", "G", "EXPENSE", "SALIDA", "PAGO", "-"):
        return Transaction.TransactionType.EXPENSE
    raise ValueError(f"Tipo inválido '{raw_val}' (use Gasto o Ingreso).")


def _parse_currency_value(raw_val):
    """Normaliza la moneda de la operación a ARS o USD."""
    val = _normalize_header(raw_val).upper()
    if not val or val in ("ARS", "$", "PESO", "PESOS", "AR$"):
        return Transaction.Currency.ARS
    if val in ("USD", "U$S", "US$", "DOLAR", "DOLARES", "USS"):
        return Transaction.Currency.USD
    raise ValueError(f"Moneda inválida '{raw_val}' (use ARS o USD).")


def _parse_amount_value(raw_val):
    """Normaliza montos contables en formato texto o numérico a Decimal(14, 2) positivo."""
    val = str(raw_val or "").strip()
    if not val or val.lower() in ("nan", "none"):
        raise ValueError("Monto vacío.")
    val = (
        val.replace("U$S", "")
        .replace("US$", "")
        .replace("ARS", "")
        .replace("USD", "")
        .replace("$", "")
        .replace(" ", "")
    )
    if "," in val and "." in val:
        if val.rfind(",") > val.rfind("."):
            val = val.replace(".", "").replace(",", ".")
        else:
            val = val.replace(",", "")
    elif "," in val:
        val = val.replace(",", ".")
    try:
        dec = abs(Decimal(val)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Monto inválido '{raw_val}'.") from exc
    if dec <= Decimal("0.00"):
        raise ValueError("El monto debe ser mayor a 0.")
    return dec


def _process_in_memory_spreadsheet(uploaded_file, user):
    """
    Procesa un archivo CSV o Excel estrictamente en memoria (io.BytesIO + pandas)
    con la estructura: Fecha, Vertical, Tipo, Concepto, Cliente, Detalle, Monto, Moneda.
    Registra automáticamente los clientes nuevos con su ID y libera el buffer de RAM.
    """
    raw_bytes = uploaded_file.read()
    buffer = io.BytesIO(raw_bytes)
    uploaded_file.close()
    df = None

    try:
        filename = (uploaded_file.name or "").lower().strip()
        if filename.endswith(".csv"):
            df = pd.read_csv(buffer, dtype=str, keep_default_na=False)
            if len(df.columns) == 1 and ";" in str(df.columns[0]):
                buffer.seek(0)
                df = pd.read_csv(buffer, sep=";", dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(buffer, dtype=str, keep_default_na=False, engine="openpyxl")

        if df is None or df.empty:
            raise ValueError("El archivo no contiene filas para procesar.")

        col_map = {}
        aliases = {
            "date": {"fecha", "date", "dia", "fec"},
            "vertical": {"vertical", "unidad", "unidad_de_negocio", "area", "sector"},
            "transaction_type": {"tipo", "type", "transaction_type", "movimiento"},
            "concept": {"concepto", "concept", "categoria", "rubro"},
            "client": {"cliente", "client", "customer", "razon_social"},
            "detail": {"detalle", "detail", "descripcion", "description", "observacion", "nota"},
            "amount": {"monto", "importe", "amount", "valor", "total"},
            "currency": {"moneda", "currency", "divisa"},
        }
        for orig_col in df.columns:
            norm_col = _normalize_header(orig_col)
            for target_field, valid_names in aliases.items():
                if norm_col in valid_names and target_field not in col_map:
                    col_map[target_field] = orig_col

        required_fields = ("date", "transaction_type", "concept", "amount")
        missing = [f for f in required_fields if f not in col_map]
        if missing:
            raise ValueError(
                "Error de validación: El archivo debe incluir al menos las columnas "
                "Fecha, Tipo, Concepto y Monto (junto con Vertical, Cliente, Detalle y Moneda)."
            )

        user_clients = list(Client.objects.filter(user=user))
        clients_by_name = {c.name.strip().lower(): c for c in user_clients}
        clients_by_id = {c.id: c for c in user_clients}

        transactions_to_create = []
        for idx, row in df.iterrows():
            row_num = idx + 2
            raw_date = str(row[col_map["date"]]).strip()
            raw_type = str(row[col_map["transaction_type"]]).strip()
            raw_concept = str(row[col_map["concept"]]).strip()
            raw_amount = str(row[col_map["amount"]]).strip()
            raw_vertical = (
                str(row[col_map["vertical"]]).strip() if "vertical" in col_map else ""
            )
            raw_detail = (
                str(row[col_map["detail"]]).strip() if "detail" in col_map else ""
            )
            raw_currency = (
                str(row[col_map["currency"]]).strip() if "currency" in col_map else "ARS"
            )

            if not any((raw_date, raw_type, raw_concept, raw_amount)):
                continue

            try:
                parsed_date = _parse_date_value(raw_date)
                parsed_type = _parse_type_value(raw_type)
                parsed_amount = _parse_amount_value(raw_amount)
                parsed_currency = _parse_currency_value(raw_currency)
            except ValueError as err:
                raise ValueError(f"Fila {row_num}: {err}") from err

            if not raw_concept:
                raise ValueError(f"Fila {row_num}: El concepto es obligatorio.")

            if raw_vertical.lower() in ("nan", "none"):
                raw_vertical = ""
            if raw_detail.lower() in ("nan", "none"):
                raw_detail = ""

            client_obj = None
            if "client" in col_map:
                raw_client = str(row[col_map["client"]]).strip()
                if raw_client and raw_client.lower() not in (
                    "nan",
                    "none",
                    "-",
                    "sin cliente",
                    "— sin cliente —",
                ):
                    if raw_client.isdigit() and int(raw_client) in clients_by_id:
                        client_obj = clients_by_id[int(raw_client)]
                    else:
                        client_key = raw_client.lower()
                        client_obj = clients_by_name.get(client_key)
                        if client_obj is None:
                            client_obj = Client.objects.create(
                                user=user, name=raw_client[:150]
                            )
                            clients_by_name[client_key] = client_obj
                            clients_by_id[client_obj.id] = client_obj

            transactions_to_create.append(
                Transaction(
                    user=user,
                    date=parsed_date,
                    vertical=raw_vertical[:120],
                    transaction_type=parsed_type,
                    concept=raw_concept[:150],
                    client=client_obj,
                    detail=raw_detail[:255],
                    amount=parsed_amount,
                    currency=parsed_currency,
                )
            )

        if not transactions_to_create:
            raise ValueError("No se encontraron registros válidos en el archivo.")

        with db_transaction.atomic():
            created = Transaction.objects.bulk_create(
                transactions_to_create, batch_size=500
            )
        return created
    finally:
        if df is not None:
            del df
        buffer.close()
        del buffer
        del raw_bytes
        gc.collect()


def _paginate_user_transactions(user, page=1, per_page=DEFAULT_PAGE_SIZE):
    """
    Ejecuta la paginación en base de datos para las transacciones del usuario
    y devuelve (page_obj, pagination_meta_dict).
    """
    per_page = max(1, min(int(per_page), MAX_PAGE_SIZE))
    qs = (
        Transaction.objects.filter(user=user)
        .select_related("client")
        .order_by("-date", "-id")
    )
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    pagination_meta = {
        "page": page_obj.number,
        "per_page": per_page,
        "total_pages": paginator.num_pages,
        "total_count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page": (
            page_obj.previous_page_number() if page_obj.has_previous() else None
        ),
        "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
        "start_index": page_obj.start_index() if paginator.count > 0 else 0,
        "end_index": page_obj.end_index() if paginator.count > 0 else 0,
    }
    return page_obj, pagination_meta


@login_required
@require_http_methods(["GET", "POST"])
def transactions_view(request):
    """
    Lista las transacciones del usuario de forma paginada (25 por defecto, máx. 100)
    y procesa peticiones POST (vía Fetch API o formulario) para crear, modificar,
    guardar en lote (Guardar Cambios), eliminar e importar CSV/Excel en memoria.
    """
    if request.method == "GET":
        page, per_page = _parse_pagination_params(request.GET)
        page_obj, pagination_meta = _paginate_user_transactions(
            request.user, page=page, per_page=per_page
        )

        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )
        if is_ajax:
            return JsonResponse(
                {
                    "status": "ok",
                    "transactions": [
                        _serialize_transaction(tx) for tx in page_obj.object_list
                    ],
                    "pagination": pagination_meta,
                }
            )

        clients = Client.objects.filter(user=request.user).order_by("name")
        form = TransactionForm(user=request.user)
        upload_form = TransactionBulkUploadForm()
        return render(
            request,
            "app/transactions.html",
            {
                "transactions": page_obj.object_list,
                "page_obj": page_obj,
                "pagination": pagination_meta,
                "per_page": per_page,
                "allowed_page_sizes": ALLOWED_PAGE_SIZES,
                "clients": clients,
                "form": form,
                "upload_form": upload_form,
            },
        )

    # Procesamiento de peticiones POST
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Formato JSON inválido."}, status=400
            )
    else:
        payload = request.POST.dict()

    page, per_page = _parse_pagination_params(payload, request.GET)
    action = payload.get("action") or (
        "bulk_upload" if "file" in request.FILES else "create"
    )

    # 1. Subida masiva en memoria (CSV / Excel con pandas)
    if action == "bulk_upload":
        upload_form = TransactionBulkUploadForm(request.POST, request.FILES)
        if not upload_form.is_valid():
            error_msg = " ".join(
                err for errs in upload_form.errors.values() for err in errs
            )
            return JsonResponse(
                {"status": "error", "message": error_msg, "errors": upload_form.errors},
                status=400,
            )
        try:
            created_records = _process_in_memory_spreadsheet(
                upload_form.cleaned_data["file"], request.user
            )
        except Exception as exc:
            return JsonResponse(
                {"status": "error", "message": str(exc)},
                status=400,
            )

        page_obj, pagination_meta = _paginate_user_transactions(
            request.user, page=1, per_page=per_page
        )
        all_clients = [
            {"id": c.id, "name": c.name}
            for c in Client.objects.filter(user=request.user).order_by("name")
        ]
        return JsonResponse(
            {
                "status": "ok",
                "message": f"Ingesta completada: {len(created_records)} transacciones procesadas en memoria.",
                "imported_count": len(created_records),
                "clients": all_clients,
                "transactions": [
                    _serialize_transaction(tx) for tx in page_obj.object_list
                ],
                "pagination": pagination_meta,
            }
        )

    # 2. Eliminación de registro individual
    if action == "delete":
        tx_id = payload.get("id")
        if not tx_id:
            return JsonResponse(
                {"status": "error", "message": "Identificador de transacción requerido."},
                status=400,
            )
        tx = get_object_or_404(Transaction, pk=tx_id, user=request.user)
        deleted_id = tx.id
        tx.delete()
        page_obj, pagination_meta = _paginate_user_transactions(
            request.user, page=page, per_page=per_page
        )
        return JsonResponse(
            {
                "status": "ok",
                "message": "Transacción eliminada correctamente.",
                "deleted_id": deleted_id,
                "transactions": [
                    _serialize_transaction(item) for item in page_obj.object_list
                ],
                "pagination": pagination_meta,
            }
        )

    # 3. Guardado masivo de ediciones manuales ("Guardar Cambios")
    if action == "bulk_save":
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            return JsonResponse(
                {"status": "error", "message": "No hay cambios pendientes para guardar."},
                status=400,
            )

        saved_instances = []
        try:
            with db_transaction.atomic():
                for idx, row_data in enumerate(rows, start=1):
                    tx_id = row_data.get("id")
                    instance = None
                    if tx_id:
                        instance = get_object_or_404(
                            Transaction, pk=tx_id, user=request.user
                        )
                    form = TransactionForm(
                        data=row_data, instance=instance, user=request.user
                    )
                    if not form.is_valid():
                        err_detail = "; ".join(
                            f"{field}: {', '.join(errs)}"
                            for field, errs in form.errors.items()
                        )
                        raise ValueError(f"Fila {idx} inválida ({err_detail}).")
                    tx_obj = form.save()
                    saved_instances.append(tx_obj)
        except ValueError as err:
            return JsonResponse(
                {"status": "error", "message": str(err)},
                status=400,
            )

        page_obj, pagination_meta = _paginate_user_transactions(
            request.user, page=page, per_page=per_page
        )
        all_clients = [
            {"id": c.id, "name": c.name}
            for c in Client.objects.filter(user=request.user).order_by("name")
        ]
        return JsonResponse(
            {
                "status": "ok",
                "message": f"Cambios confirmados: {len(saved_instances)} registro(s) guardado(s).",
                "clients": all_clients,
                "saved_transactions": [_serialize_transaction(tx) for tx in saved_instances],
                "transactions": [
                    _serialize_transaction(tx) for tx in page_obj.object_list
                ],
                "pagination": pagination_meta,
            }
        )

    # 4. Creación o modificación individual (ModelForm)
    instance = None
    if action == "update":
        tx_id = payload.get("id")
        if not tx_id:
            return JsonResponse(
                {"status": "error", "message": "ID de transacción requerido para modificar."},
                status=400,
            )
        instance = get_object_or_404(Transaction, pk=tx_id, user=request.user)

    form = TransactionForm(data=payload, instance=instance, user=request.user)
    if form.is_valid():
        tx_obj = form.save()
        status_code = 200 if instance else 201
        all_clients = [
            {"id": c.id, "name": c.name}
            for c in Client.objects.filter(user=request.user).order_by("name")
        ]
        return JsonResponse(
            {
                "status": "ok",
                "message": (
                    "Transacción actualizada correctamente."
                    if instance
                    else "Transacción creada correctamente."
                ),
                "clients": all_clients,
                "transaction": _serialize_transaction(tx_obj),
            },
            status=status_code,
        )

    error_summary = "; ".join(
        f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()
    )
    return JsonResponse(
        {
            "status": "error",
            "message": f"Error de validación ({error_summary}).",
            "errors": form.errors,
        },
        status=400,
    )


@login_required
@require_http_methods(["GET"])
def metrics_view(request):
    """Interfaz de Métricas para usuarios autenticados."""
    return render(request, "app/metrics.html")


class CustomLoginView(LoginView):
    """Vista de inicio de sesión con formulario basado en email y redirección si ya está autenticado."""

    template_name = "app/auth/login.html"
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    """Vista de cierre de sesión restringida exclusivamente al método POST."""

    http_method_names = ["post", "options"]
    next_page = reverse_lazy("app:login")


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Vista de registro de nuevos usuarios.
    Crea la cuenta con is_active=False y despacha el correo de confirmación.
    """
    if request.user.is_authenticated:
        return redirect("app:dashboard")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            send_activation_email(request, user)
            return redirect("app:verify_email_sent")
    else:
        form = CustomUserCreationForm()

    return render(request, "app/auth/register.html", {"form": form})


@require_http_methods(["GET"])
def verify_email_sent_view(request):
    """Vista informativa tras enviar el enlace de activación por correo electrónico."""
    return render(request, "app/auth/verify_email_sent.html")


@require_http_methods(["GET"])
def activate_account_view(request, uidb64, token):
    """
    Verifica el token de activación enviado por correo electrónico.
    Si es válido, activa la cuenta y redirige al login; de lo contrario, muestra error.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        messages.success(
            request,
            "Cuenta activada correctamente. Ya puede iniciar sesión.",
        )
        return redirect("app:login")

    return render(request, "app/auth/verify_email_invalid.html", status=400)


@require_http_methods(["GET", "POST"])
def resend_activation_view(request):
    """
    Permite solicitar un nuevo enlace de activación para cuentas inactivas.
    Implementa rate-limit en memoria (120 segundos) y protección contra enumeración.
    """
    if request.method == "POST":
        form = ResendActivationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            cache_key = f"resend_cooldown_{email}"

            if cache.get(cache_key):
                cooldown_msg = (
                    "Debe aguardar 2 minutos antes de solicitar otro enlace de activación."
                )
                form.add_error(None, cooldown_msg)
                messages.error(request, cooldown_msg)
                return render(
                    request,
                    "app/auth/resend_activation.html",
                    {"form": form},
                )

            user = CustomUser.objects.filter(
                email__iexact=email, is_active=False
            ).first()
            if user is not None:
                send_activation_email(request, user)
                cache.set(cache_key, True, timeout=120)

            return redirect("app:verify_email_sent")
    else:
        initial_email = request.GET.get("email", "").strip().lower()
        form = ResendActivationForm(
            initial={"email": initial_email} if initial_email else None
        )

    return render(request, "app/auth/resend_activation.html", {"form": form})


class CustomPasswordResetView(PasswordResetView):
    """Paso 1: Solicitud de recuperación de contraseña por correo electrónico."""

    template_name = "app/auth/password_reset_form.html"
    email_template_name = "app/auth/emails/password_reset_email.txt"
    subject_template_name = "app/auth/emails/password_reset_subject.txt"
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy("app:password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Paso 2: Confirmación de despacho de instrucciones de recuperación."""

    template_name = "app/auth/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Paso 3: Ingreso de la nueva contraseña validando UID y token."""

    template_name = "app/auth/password_reset_confirm.html"
    form_class = CustomSetPasswordForm
    success_url = reverse_lazy("app:password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Paso 4: Confirmación final de restablecimiento de contraseña."""

    template_name = "app/auth/password_reset_complete.html"
