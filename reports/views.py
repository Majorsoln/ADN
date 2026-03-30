from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from decimal import Decimal
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from projects.models import Project, ActivityLog
from .models import Invoice, InvoiceItem, Quote, QuoteItem, ProjectReport
from .forms import InvoiceForm, InvoiceItemForm, QuoteForm


def format_tzs(amount):
    return f"TZS {amount:,.2f}"


@login_required
def reports_dashboard(request):
    invoices = Invoice.objects.select_related('project').all()
    quotes = Quote.objects.select_related('project').all()
    reports = ProjectReport.objects.select_related('project').all()

    context = {
        'invoices': invoices,
        'quotes': quotes,
        'reports': reports,
        'invoice_count': invoices.count(),
        'quote_count': quotes.count(),
        'report_count': reports.count(),
    }
    return render(request, 'reports/reports_dashboard.html', context)


@login_required
def create_invoice(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            ActivityLog.objects.create(
                project=invoice.project, user=request.user,
                action=f'Created invoice INV-{invoice.invoice_number}'
            )
            messages.success(request, f'Invoice INV-{invoice.invoice_number} created.')
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm()
    return render(request, 'reports/invoice_form.html', {'form': form, 'title': 'Create Invoice'})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()
    item_form = InvoiceItemForm()
    context = {
        'invoice': invoice,
        'items': items,
        'item_form': item_form,
    }
    return render(request, 'reports/invoice_detail.html', context)


@login_required
def add_invoice_item(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        form = InvoiceItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.invoice = invoice
            item.save()
            total = sum(i.total for i in invoice.items.all())
            invoice.total_amount = total
            invoice.save()
            messages.success(request, 'Item added to invoice.')
    return redirect('invoice_detail', pk=pk)


@login_required
def generate_invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('InvTitle', parent=styles['Title'], fontSize=24, textColor=colors.HexColor('#1a2e5a'), spaceAfter=5*mm)
    header_style = ParagraphStyle('InvHeader', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2176ae'))
    normal_style = ParagraphStyle('InvNormal', parent=styles['Normal'], fontSize=10)
    right_style = ParagraphStyle('InvRight', parent=styles['Normal'], fontSize=10, alignment=TA_RIGHT)

    elements = []

    elements.append(Paragraph("ADN uPVC & Aluminum Solutions", title_style))
    elements.append(Paragraph("Professional Windows & Doors", ParagraphStyle('Sub', parent=styles['Normal'], fontSize=10, textColor=colors.grey)))
    elements.append(Spacer(1, 5*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2176ae')))
    elements.append(Spacer(1, 5*mm))

    elements.append(Paragraph(f"INVOICE #{invoice.invoice_number}", ParagraphStyle('InvNum', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a2e5a'))))
    elements.append(Spacer(1, 3*mm))

    info_data = [
        ['Client:', invoice.client_name, 'Date:', str(invoice.issue_date)],
        ['Address:', invoice.client_address or 'N/A', 'Due Date:', str(invoice.due_date) if invoice.due_date else 'N/A'],
        ['Project:', invoice.project.title, 'Status:', invoice.get_status_display()],
    ]
    info_table = Table(info_data, colWidths=[60, 200, 60, 150])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 8*mm))

    if invoice.description:
        elements.append(Paragraph("Description", header_style))
        elements.append(Paragraph(invoice.description, normal_style))
        elements.append(Spacer(1, 5*mm))

    elements.append(Paragraph("Items", header_style))
    elements.append(Spacer(1, 3*mm))

    table_data = [['#', 'Description', 'Qty', 'Unit Price (TZS)', 'Total (TZS)']]
    for i, item in enumerate(items, 1):
        table_data.append([
            str(i),
            item.description,
            f"{item.quantity:,.2f}",
            f"{item.unit_price:,.2f}",
            f"{item.total:,.2f}",
        ])
    table_data.append(['', '', '', 'TOTAL:', f"{invoice.total_amount:,.2f}"])

    items_table = Table(table_data, colWidths=[30, 220, 50, 90, 90])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (3, -1), (-1, -1), 11),
        ('LINEABOVE', (3, -1), (-1, -1), 2, colors.HexColor('#1a2e5a')),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 15*mm))

    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph("Payment Methods: Bank Transfer (NMB/CRDB) | Mobile Money (M-Pesa/Tigo Pesa) | Cash",
                              ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))
    elements.append(Paragraph("ADN uPVC & Aluminum Solutions | Dar es Salaam, Tanzania | +255 xxx xxx xxx",
                              ParagraphStyle('Footer2', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ADN_Invoice_{invoice.invoice_number}.pdf"'
    return response


@login_required
def generate_project_report_pdf(request, pk):
    project = get_object_or_404(Project, pk=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('PrjTitle', parent=styles['Title'], fontSize=22, textColor=colors.HexColor('#1a2e5a'), spaceAfter=3*mm)
    h2_style = ParagraphStyle('PrjH2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2176ae'), spaceBefore=8*mm, spaceAfter=3*mm)
    normal = ParagraphStyle('PrjNormal', parent=styles['Normal'], fontSize=10)

    elements = []

    elements.append(Paragraph("ADN uPVC & Aluminum Solutions", title_style))
    elements.append(Paragraph("PROJECT REPORT", ParagraphStyle('Sub', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#667eea'), alignment=TA_CENTER)))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2176ae')))
    elements.append(Spacer(1, 5*mm))

    elements.append(Paragraph("Project Information", h2_style))
    info = [
        ['Project Title:', project.title],
        ['Client:', project.client_name],
        ['Location:', project.location or 'N/A'],
        ['Status:', project.get_status_display()],
        ['Priority:', project.get_priority_display()],
        ['Start Date:', str(project.start_date)],
        ['End Date:', str(project.end_date) if project.end_date else 'N/A'],
        ['Completion:', f'{project.completion_percentage}%'],
        ['Budget:', format_tzs(project.budget)],
    ]
    info_table = Table(info, colWidths=[120, 350])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(info_table)

    materials = project.materials.all()
    if materials:
        elements.append(Paragraph("Materials Used", h2_style))
        mat_data = [['Material', 'Qty', 'Unit', 'Unit Price', 'Total']]
        for m in materials:
            mat_data.append([m.name, f"{m.quantity:,.1f}", m.unit, format_tzs(m.unit_price), format_tzs(m.total_cost)])
        mat_data.append(['', '', '', 'TOTAL:', format_tzs(project.total_material_cost)])

        mat_table = Table(mat_data, colWidths=[160, 50, 40, 100, 120])
        mat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (3, -1), (-1, -1), 1, colors.HexColor('#1a2e5a')),
        ]))
        elements.append(mat_table)

    labor = project.labor_costs.all()
    if labor:
        elements.append(Paragraph("Labor Costs", h2_style))
        lab_data = [['Description', 'Worker', 'Days', 'Rate', 'Amount']]
        for l in labor:
            lab_data.append([l.description, l.worker_name, str(l.days), format_tzs(l.daily_rate), format_tzs(l.amount)])
        lab_data.append(['', '', '', 'TOTAL:', format_tzs(project.total_labor_cost)])

        lab_table = Table(lab_data, colWidths=[140, 90, 40, 100, 100])
        lab_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (3, -1), (-1, -1), 1, colors.HexColor('#1a2e5a')),
        ]))
        elements.append(lab_table)

    transport = project.transport_costs.all()
    if transport:
        elements.append(Paragraph("Transport Costs", h2_style))
        tr_data = [['Vehicle', 'From', 'To', 'Cost']]
        for t in transport:
            tr_data.append([t.vehicle_type, t.from_location, t.to_location, format_tzs(t.cost)])
        tr_data.append(['', '', 'TOTAL:', format_tzs(project.total_transport_cost)])

        tr_table = Table(tr_data, colWidths=[100, 130, 130, 110])
        tr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (2, -1), (-1, -1), 1, colors.HexColor('#1a2e5a')),
        ]))
        elements.append(tr_table)

    elements.append(Paragraph("Financial Summary", h2_style))
    profit_color = colors.HexColor('#27ae60') if project.profit_loss >= 0 else colors.HexColor('#e74c3c')
    fin_data = [
        ['Total Material Cost:', format_tzs(project.total_material_cost)],
        ['Total Labor Cost:', format_tzs(project.total_labor_cost)],
        ['Total Transport Cost:', format_tzs(project.total_transport_cost)],
        ['Total Other Expenses:', format_tzs(project.total_other_expenses)],
        ['TOTAL EXPENSES:', format_tzs(project.total_expenses)],
        ['', ''],
        ['Total Revenue (Payments):', format_tzs(project.total_revenue)],
        ['Budget:', format_tzs(project.budget)],
        ['', ''],
        ['PROFIT / LOSS:', format_tzs(project.profit_loss)],
        ['Profit Margin:', f'{project.profit_margin:.1f}%'],
    ]

    fin_table = Table(fin_data, colWidths=[200, 270])
    fin_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 4), (-1, 4), 11),
        ('LINEABOVE', (0, 4), (-1, 4), 1, colors.HexColor('#1a2e5a')),
        ('FONTNAME', (0, 9), (-1, 9), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 9), (-1, 10), 12),
        ('TEXTCOLOR', (1, 9), (1, 9), profit_color),
        ('LINEABOVE', (0, 9), (-1, 9), 2, colors.HexColor('#1a2e5a')),
    ]))
    elements.append(fin_table)

    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph(
        f"Report generated on {timezone.now().strftime('%Y-%m-%d %H:%M')} | ADN uPVC & Aluminum Solutions",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)

    report_obj = ProjectReport.objects.create(
        project=project,
        title=f'Project Report - {project.title}',
        summary=f'Auto-generated report for {project.title}',
        prepared_by=request.user,
    )

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ADN_Project_Report_{project.pk}.pdf"'
    return response


@login_required
def generate_quote_pdf(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    items = quote.items.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('QtTitle', parent=styles['Title'], fontSize=22, textColor=colors.HexColor('#1a2e5a'), spaceAfter=3*mm)
    h2_style = ParagraphStyle('QtH2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2176ae'), spaceBefore=5*mm, spaceAfter=3*mm)

    elements = []

    elements.append(Paragraph("ADN uPVC & Aluminum Solutions", title_style))
    elements.append(Paragraph("QUOTATION", ParagraphStyle('Sub', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#667eea'), alignment=TA_CENTER)))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2176ae')))
    elements.append(Spacer(1, 5*mm))

    info = [
        ['Quote #:', quote.quote_number, 'Date:', str(quote.created_at.date())],
        ['Client:', quote.client_name, 'Valid Until:', str(quote.valid_until) if quote.valid_until else 'N/A'],
        ['Project:', quote.project_name, 'Status:', quote.get_status_display()],
    ]
    info_table = Table(info, colWidths=[60, 200, 70, 140])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5*mm))

    if items.exists():
        elements.append(Paragraph("Items", h2_style))
        table_data = [['#', 'Description', 'Size', 'Qty', 'Material', 'Unit Price', 'Total']]
        for i, item in enumerate(items, 1):
            size = f"{item.width}x{item.height}" if item.width and item.height else '-'
            table_data.append([
                str(i), item.description, size, str(item.quantity),
                item.material or '-', format_tzs(item.unit_price), format_tzs(item.total)
            ])
        table_data.append(['', '', '', '', '', 'TOTAL:', format_tzs(quote.total_amount)])

        items_table = Table(table_data, colWidths=[25, 130, 60, 30, 70, 80, 80])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (5, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (5, -1), (-1, -1), 10),
            ('LINEABOVE', (5, -1), (-1, -1), 2, colors.HexColor('#1a2e5a')),
        ]))
        elements.append(items_table)

    if quote.notes:
        elements.append(Spacer(1, 5*mm))
        elements.append(Paragraph("Notes", h2_style))
        elements.append(Paragraph(quote.notes, ParagraphStyle('Notes', parent=styles['Normal'], fontSize=9)))

    elements.append(Spacer(1, 15*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph("Terms: 50% deposit required. Balance due on completion. Quote valid for 30 days.",
                              ParagraphStyle('Terms', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))
    elements.append(Paragraph("ADN uPVC & Aluminum Solutions | Dar es Salaam, Tanzania",
                              ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ADN_Quote_{quote.quote_number}.pdf"'
    return response


@login_required
def create_quote(request):
    if request.method == 'POST':
        form = QuoteForm(request.POST)
        if form.is_valid():
            quote = form.save(commit=False)
            quote.created_by = request.user
            quote.save()
            messages.success(request, f'Quote QT-{quote.quote_number} created.')
            return redirect('reports_dashboard')
    else:
        form = QuoteForm()
    return render(request, 'reports/quote_form.html', {'form': form, 'title': 'Create Quote'})


@login_required
def financial_summary_pdf(request):
    """Generate a comprehensive financial summary PDF across all projects."""
    projects = Project.objects.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('FinTitle', parent=styles['Title'], fontSize=22, textColor=colors.HexColor('#1a2e5a'), spaceAfter=3*mm)
    h2_style = ParagraphStyle('FinH2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2176ae'), spaceBefore=8*mm, spaceAfter=3*mm)

    elements = []

    elements.append(Paragraph("ADN uPVC & Aluminum Solutions", title_style))
    elements.append(Paragraph("FINANCIAL SUMMARY REPORT", ParagraphStyle('Sub', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#667eea'), alignment=TA_CENTER)))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%B %d, %Y')}", ParagraphStyle('Date', parent=styles['Normal'], fontSize=10, textColor=colors.grey, alignment=TA_CENTER)))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2176ae')))
    elements.append(Spacer(1, 5*mm))

    elements.append(Paragraph("Project Overview", h2_style))
    proj_data = [['Project', 'Client', 'Status', 'Budget', 'Expenses', 'Revenue', 'Profit/Loss']]
    grand_budget = Decimal('0')
    grand_expenses = Decimal('0')
    grand_revenue = Decimal('0')
    grand_profit = Decimal('0')

    for p in projects:
        expenses = p.total_expenses
        revenue = p.total_revenue
        profit = revenue - expenses
        grand_budget += p.budget
        grand_expenses += expenses
        grand_revenue += revenue
        grand_profit += profit

        proj_data.append([
            Paragraph(p.title[:25], ParagraphStyle('Cell', fontSize=7)),
            p.client_name[:15],
            p.get_status_display(),
            format_tzs(p.budget),
            format_tzs(expenses),
            format_tzs(revenue),
            format_tzs(profit),
        ])

    proj_data.append(['', '', 'TOTALS:', format_tzs(grand_budget), format_tzs(grand_expenses), format_tzs(grand_revenue), format_tzs(grand_profit)])

    proj_table = Table(proj_data, colWidths=[85, 55, 55, 75, 75, 75, 75])
    proj_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a2e5a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#1a2e5a')),
    ]))
    elements.append(proj_table)

    elements.append(Paragraph("Summary", h2_style))
    profit_color = colors.HexColor('#27ae60') if grand_profit >= 0 else colors.HexColor('#e74c3c')
    summary = [
        ['Total Projects:', str(projects.count())],
        ['Total Budget:', format_tzs(grand_budget)],
        ['Total Expenses:', format_tzs(grand_expenses)],
        ['Total Revenue:', format_tzs(grand_revenue)],
        ['Net Profit/Loss:', format_tzs(grand_profit)],
    ]
    sum_table = Table(summary, colWidths=[200, 270])
    sum_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (1, -1), (1, -1), profit_color),
        ('FONTSIZE', (0, -1), (-1, -1), 13),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#1a2e5a')),
    ]))
    elements.append(sum_table)

    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    elements.append(Paragraph(
        f"Confidential | ADN uPVC & Aluminum Solutions | {timezone.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="ADN_Financial_Summary.pdf"'
    return response
