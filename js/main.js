/* =========================================================
   GRAVITY FITNESS — site interactions
   ========================================================= */

/* ===== Config — EDIT THESE FOR YOUR GYM ===== */
const GYM_WHATSAPP_NUMBER = '917999526112'; // country code + number, no '+' or spaces
const GYM_UPI_ID = 'gravityfitness@upi';     // replace with real UPI ID (e.g. yourname@bankupi)
const GYM_NAME = 'Gravity Fitness';
const GYM_ADDRESS = 'CRPF Road, Above Canara Bank, Neemuch, Madhya Pradesh';
const GYM_GSTIN = ''; // optional — leave blank if not registered

// Razorpay key — get this from Razorpay Dashboard > Settings > API Keys (use the LIVE key_id)
// Until this is set, "Pay Online (Razorpay)" will fall back to the UPI option automatically.
const RAZORPAY_KEY_ID = ''; // e.g. 'rzp_live_XXXXXXXXXXXX'

/* ===== Mobile nav ===== */
const toggle = document.getElementById('menuToggle');
const nav = document.getElementById('nav');
toggle.addEventListener('click', () => nav.classList.toggle('open'));
document.querySelectorAll('nav a').forEach(a => a.addEventListener('click', () => nav.classList.remove('open')));

/* ===== Scroll reveal ===== */
const reveals = document.querySelectorAll('.reveal');
const obs = new IntersectionObserver((entries) => {
  entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
}, { threshold: 0.15 });
reveals.forEach(r => obs.observe(r));

/* =========================================================
   MODAL HELPERS
   ========================================================= */
function openModal(overlay) {
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeModal(overlay, form) {
  overlay.classList.remove('open');
  document.body.style.overflow = '';
  if (form) form.reset();
}
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.remove('open');
    if (!document.querySelector('.modal-overlay.open')) document.body.style.overflow = '';
  });
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(o => o.classList.remove('open'));
    document.body.style.overflow = '';
  }
});

/* =========================================================
   INVOICE NUMBER GENERATOR (persisted in localStorage)
   ========================================================= */
function getNextInvoiceNumber() {
  const key = 'gf_invoice_seq';
  let seq = parseInt(localStorage.getItem(key) || '1000', 10);
  seq += 1;
  localStorage.setItem(key, seq.toString());
  const year = new Date().getFullYear();
  return `GF-${year}-${seq}`;
}

function formatDate(d) {
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

/* =========================================================
   BUY PACKAGE MODAL
   ========================================================= */
const modalOverlay = document.getElementById('modalOverlay');
const modalClose = document.getElementById('modalClose');
const modalPlan = document.getElementById('modalPlan');
const buyForm = document.getElementById('buyForm');
const custName = document.getElementById('custName');
const custPhone = document.getElementById('custPhone');
const custEmail = document.getElementById('custEmail');
const custMessage = document.getElementById('custMessage');

let selectedPlan = '';
let selectedDuration = '';
let selectedAmount = 0;

document.querySelectorAll('.buy-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    selectedPlan = btn.dataset.plan;
    selectedDuration = btn.dataset.duration;
    selectedAmount = parseInt(btn.dataset.amount, 10);
    modalPlan.textContent = `Plan: ${selectedPlan} — ₹${selectedAmount} (${selectedDuration})`;
    openModal(modalOverlay);
    setTimeout(() => custName.focus(), 300);
  });
});

modalClose.addEventListener('click', () => closeModal(modalOverlay, buyForm));

buyForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const payMethod = e.submitter ? e.submitter.dataset.pay : 'cash';

  const customer = {
    name: custName.value.trim(),
    phone: custPhone.value.trim(),
    email: custEmail.value.trim(),
    message: custMessage.value.trim()
  };

  if (payMethod === 'razorpay') {
    payWithRazorpay(customer);
  } else if (payMethod === 'upi') {
    payWithUPI(customer);
  } else {
    reserveWithoutPayment(customer);
  }
});

/* ---- Option A: Razorpay Checkout ---- */
function payWithRazorpay(customer) {
  if (!RAZORPAY_KEY_ID) {
    alert('Online card/UPI checkout via Razorpay is being set up. Redirecting you to UPI payment instead.');
    payWithUPI(customer);
    return;
  }

  const options = {
    key: RAZORPAY_KEY_ID,
    amount: selectedAmount * 100, // paise
    currency: 'INR',
    name: GYM_NAME,
    description: `${selectedPlan} (${selectedDuration})`,
    prefill: {
      name: customer.name,
      contact: customer.phone,
      email: customer.email
    },
    theme: { color: '#d4ff3f' },
    handler: function (response) {
      closeModal(modalOverlay, buyForm);
      showInvoice({
        customer,
        plan: selectedPlan,
        duration: selectedDuration,
        amount: selectedAmount,
        paymentMethod: 'Razorpay',
        paymentRef: response.razorpay_payment_id || '—',
        status: 'paid'
      });
    },
    modal: {
      ondismiss: function () { /* user closed popup */ }
    }
  };

  const rzp = new Razorpay(options);
  rzp.open();
}

/* ---- Option B: UPI deep link ---- */
function payWithUPI(customer) {
  const note = encodeURIComponent(`${selectedPlan} - ${customer.name}`);
  const upiUrl = `upi://pay?pa=${GYM_UPI_ID}&pn=${encodeURIComponent(GYM_NAME)}&am=${selectedAmount}&cu=INR&tn=${note}`;

  window.location.href = upiUrl;
  closeModal(modalOverlay, buyForm);

  showInvoice({
    customer,
    plan: selectedPlan,
    duration: selectedDuration,
    amount: selectedAmount,
    paymentMethod: 'UPI',
    paymentRef: 'Pending confirmation',
    status: 'pending'
  });
}

/* ---- Option C: Reserve, pay at gym ---- */
function reserveWithoutPayment(customer) {
  closeModal(modalOverlay, buyForm);
  showInvoice({
    customer,
    plan: selectedPlan,
    duration: selectedDuration,
    amount: selectedAmount,
    paymentMethod: 'Cash / Card at Gym',
    paymentRef: 'To be collected at gym',
    status: 'pending'
  });
}

/* =========================================================
   FREE DAY BOOKING MODAL
   ========================================================= */
const freeDayOverlay = document.getElementById('freeDayOverlay');
const freeDayClose = document.getElementById('freeDayClose');
const freeDayForm = document.getElementById('freeDayForm');
const freeDayBtn = document.getElementById('freeDayBtn');
const freeName = document.getElementById('freeName');
const freePhone = document.getElementById('freePhone');
const freeDate = document.getElementById('freeDate');
const freeSlot = document.getElementById('freeSlot');

freeDayBtn.addEventListener('click', () => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  freeDate.min = new Date().toISOString().split('T')[0];
  if (!freeDate.value) freeDate.value = tomorrow.toISOString().split('T')[0];
  openModal(freeDayOverlay);
  setTimeout(() => freeName.focus(), 300);
});

freeDayClose.addEventListener('click', () => closeModal(freeDayOverlay, freeDayForm));

freeDayForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const name = freeName.value.trim();
  const phone = freePhone.value.trim();
  const date = freeDate.value;
  const slot = freeSlot.value;
  const dateFormatted = formatDate(new Date(date));

  let text = `Hi ${GYM_NAME}! I'd like to book my FREE trial day.\n\n`;
  text += `Name: ${name}\n`;
  text += `Phone: ${phone}\n`;
  text += `Preferred Date: ${dateFormatted}\n`;
  text += `Time Slot: ${slot}\n`;
  text += `\nPlease confirm my booking. Thank you!`;

  const url = `https://wa.me/${GYM_WHATSAPP_NUMBER}?text=${encodeURIComponent(text)}`;
  window.open(url, '_blank');
  closeModal(freeDayOverlay, freeDayForm);
});

/* =========================================================
   INVOICE GENERATION
   ========================================================= */
const invoiceOverlay = document.getElementById('invoiceOverlay');
const invoiceClose = document.getElementById('invoiceClose');
const invoiceContent = document.getElementById('invoiceContent');
const downloadInvoiceBtn = document.getElementById('downloadInvoiceBtn');
const invoiceWhatsappBtn = document.getElementById('invoiceWhatsappBtn');

let currentInvoice = null;

invoiceClose.addEventListener('click', () => closeModal(invoiceOverlay));

function showInvoice({ customer, plan, duration, amount, paymentMethod, paymentRef, status }) {
  const invoiceNo = getNextInvoiceNumber();
  const today = new Date();
  const gst = 0;
  const total = amount;

  currentInvoice = {
    invoiceNo, date: today, customer, plan, duration, amount, gst, total, paymentMethod, paymentRef, status
  };

  const statusLabel = status === 'paid' ? 'PAID' : 'PAYMENT PENDING';
  const statusClass = status === 'paid' ? 'paid' : 'pending';

  invoiceContent.innerHTML = `
    <div class="invoice-paper" id="invoicePaper">
      <div class="inv-header">
        <div>
          <div class="inv-brand">Gravity<span>Fit</span></div>
          <div style="font-size:.75rem;color:#777;margin-top:4px;">${GYM_ADDRESS}</div>
          ${GYM_GSTIN ? `<div style="font-size:.75rem;color:#777;">GSTIN: ${GYM_GSTIN}</div>` : ''}
        </div>
        <div class="inv-meta">
          <div><b>Invoice No:</b> ${invoiceNo}</div>
          <div><b>Date:</b> ${formatDate(today)}</div>
          <div style="margin-top:8px;"><span class="inv-status ${statusClass}">${statusLabel}</span></div>
        </div>
      </div>

      <div class="inv-section">
        <h4>Billed To</h4>
        <div>${customer.name}</div>
        <div>${customer.phone}${customer.email ? ' · ' + customer.email : ''}</div>
      </div>

      <table>
        <thead>
          <tr><th>Description</th><th>Duration</th><th>Amount</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>${plan}</td>
            <td>${duration}</td>
            <td>₹${amount.toLocaleString('en-IN')}</td>
          </tr>
          ${gst > 0 ? `<tr><td colspan="2">GST</td><td>₹${gst}</td></tr>` : ''}
          <tr class="inv-total-row">
            <td colspan="2">Total</td>
            <td>₹${total.toLocaleString('en-IN')}</td>
          </tr>
        </tbody>
      </table>

      <div class="inv-section">
        <h4>Payment Details</h4>
        <div>Method: ${paymentMethod}</div>
        <div>Reference: ${paymentRef}</div>
      </div>

      ${customer.message ? `<div class="inv-section"><h4>Note</h4><div>${customer.message}</div></div>` : ''}

      <div class="inv-footer">
        Thank you for choosing ${GYM_NAME}!<br>
        This is a computer-generated invoice. For queries, contact us via WhatsApp or visit the front desk.
        ${status === 'pending' ? '<br><b>Please complete payment at the front desk to activate your membership.</b>' : ''}
      </div>
    </div>
  `;

  openModal(invoiceOverlay);

  let waText = `Hi ${GYM_NAME}! Here's my membership booking:\n\n`;
  waText += `Invoice No: ${invoiceNo}\n`;
  waText += `Plan: ${plan} (${duration})\n`;
  waText += `Amount: ₹${total}\n`;
  waText += `Name: ${customer.name}\n`;
  waText += `Phone: ${customer.phone}\n`;
  waText += `Payment: ${paymentMethod} (${paymentRef})\n`;
  if (customer.message) waText += `Note: ${customer.message}\n`;
  invoiceWhatsappBtn.href = `https://wa.me/${GYM_WHATSAPP_NUMBER}?text=${encodeURIComponent(waText)}`;
}

/* ---- Download invoice as PDF using jsPDF ---- */
downloadInvoiceBtn.addEventListener('click', () => {
  if (!currentInvoice) return;
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const inv = currentInvoice;

  const marginX = 50;
  let y = 60;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(22);
  doc.text('GravityFit', marginX, y);
  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(110);
  y += 18;
  doc.text(GYM_ADDRESS, marginX, y);
  if (GYM_GSTIN) { y += 14; doc.text(`GSTIN: ${GYM_GSTIN}`, marginX, y); }

  doc.setTextColor(0);
  doc.setFontSize(10);
  doc.text(`Invoice No: ${inv.invoiceNo}`, 545, 60, { align: 'right' });
  doc.text(`Date: ${formatDate(inv.date)}`, 545, 75, { align: 'right' });
  doc.setFont('helvetica', 'bold');
  if (inv.status === 'paid') doc.setTextColor(90, 140, 0); else doc.setTextColor(180, 120, 0);
  doc.text(inv.status === 'paid' ? 'PAID' : 'PAYMENT PENDING', 545, 92, { align: 'right' });
  doc.setTextColor(0);

  y = 110;
  doc.setDrawColor(212, 255, 63);
  doc.setLineWidth(2);
  doc.line(marginX, y, 545, y);
  y += 30;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('BILLED TO', marginX, y);
  y += 16;
  doc.setFont('helvetica', 'normal');
  doc.text(inv.customer.name, marginX, y);
  y += 14;
  doc.text(`${inv.customer.phone}${inv.customer.email ? '  -  ' + inv.customer.email : ''}`, marginX, y);
  y += 40;

  doc.setFillColor(245, 245, 245);
  doc.rect(marginX, y - 14, 495, 24, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.text('DESCRIPTION', marginX + 10, y + 2);
  doc.text('DURATION', 330, y + 2);
  doc.text('AMOUNT', 545, y + 2, { align: 'right' });
  y += 34;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(11);
  doc.text(inv.plan, marginX + 10, y);
  doc.text(inv.duration, 330, y);
  doc.text(`Rs. ${inv.amount.toLocaleString('en-IN')}`, 545, y, { align: 'right' });
  y += 20;

  doc.setDrawColor(0);
  doc.setLineWidth(1);
  doc.line(marginX, y, 545, y);
  y += 24;
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.text('TOTAL', marginX + 10, y);
  doc.text(`Rs. ${inv.total.toLocaleString('en-IN')}`, 545, y, { align: 'right' });
  y += 50;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('PAYMENT DETAILS', marginX, y);
  y += 16;
  doc.setFont('helvetica', 'normal');
  doc.text(`Method: ${inv.paymentMethod}`, marginX, y);
  y += 14;
  doc.text(`Reference: ${inv.paymentRef}`, marginX, y);
  y += 40;

  if (inv.customer.message) {
    doc.setFont('helvetica', 'bold');
    doc.text('NOTE', marginX, y);
    y += 16;
    doc.setFont('helvetica', 'normal');
    doc.text(doc.splitTextToSize(inv.customer.message, 495), marginX, y);
    y += 40;
  }

  doc.setDrawColor(230);
  doc.line(marginX, y, 545, y);
  y += 24;
  doc.setFontSize(9);
  doc.setTextColor(140);
  doc.text(`Thank you for choosing ${GYM_NAME}!`, 297.5, y, { align: 'center' });
  y += 14;
  doc.text('This is a computer-generated invoice.', 297.5, y, { align: 'center' });
  if (inv.status === 'pending') {
    y += 14;
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(180, 120, 0);
    doc.text('Please complete payment at the front desk to activate your membership.', 297.5, y, { align: 'center' });
  }

  doc.save(`${inv.invoiceNo}.pdf`);
});
