(() => {
  'use strict';
  const core = () => window.GravityAdminCore;
  const MAX_PHOTO_DIMENSION = 720;
  const MAX_PHOTO_BYTES = 700 * 1024;

  function formatDate(value) {
    const n = Number(value || 0);
    if (!n) return '--';
    const date = new Date(n < 10_000_000_000 ? n * 1000 : n);
    return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function money(paise) {
    const value = Math.max(0, Number(paise || 0)) / 100;
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value);
  }

  function phoneDigits(value) {
    let digits = String(value || '').replace(/\D/g, '');
    if (digits.length === 10) digits = `91${digits}`;
    return digits;
  }
  async function imageFromFile(file) {
    if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Choose a JPG, PNG or WebP image.');
    if (typeof createImageBitmap === 'function') return createImageBitmap(file);
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      return image;
    } finally { URL.revokeObjectURL(url); }
  }

  async function preparePhoto(file) {
    const image = await imageFromFile(file);
    const scale = Math.min(1, MAX_PHOTO_DIMENSION / Math.max(image.width, image.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const ctx = canvas.getContext('2d');
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    if (typeof image.close === 'function') image.close();
    let blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.82));
    if (!blob) throw new Error('Could not prepare the customer photo.');
    if (blob.size > MAX_PHOTO_BYTES) blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.65));
    if (!blob || blob.size > MAX_PHOTO_BYTES) throw new Error('Photo is still too large after compression. Choose a smaller image.');
    return blob;
  }

  async function uploadPhoto(customerId, blob) {
    if (!customerId || !blob) return;
    await core().api(`/api/admin/customers/${encodeURIComponent(customerId)}/photo`, {
      method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg' }
    });
  }

  async function fetchPhoto(customerId) {
    const response = await fetch(`/api/admin/customers/${encodeURIComponent(customerId)}/photo`, { credentials: 'same-origin' });
    return response.ok ? response.blob() : null;
  }

  async function blobToImage(blob) {
    if (!blob) return null;
    if (typeof createImageBitmap === 'function') return createImageBitmap(blob);
    const url = URL.createObjectURL(blob);
    const image = new Image(); image.src = url; await image.decode();
    image._gravityUrl = url; return image;
  }
  function drawLine(ctx, y) { ctx.strokeStyle = '#d6d6d6'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(44, y); ctx.lineTo(676, y); ctx.stroke(); }
  function pair(ctx, label, value, y, bold = false) {
    ctx.fillStyle = '#222'; ctx.font = '26px Arial'; ctx.textAlign = 'left'; ctx.fillText(label, 48, y);
    ctx.textAlign = 'right'; ctx.font = `${bold ? '700 ' : ''}26px Arial`; ctx.fillText(value, 672, y); ctx.textAlign = 'left';
  }

  function receiptNumber(data) {
    const raw = String(data.payment?.id || data.membership?.membershipNumber || data.customer?.id || '').replace(/[^a-z0-9]/gi, '').toUpperCase();
    return `GF${raw.slice(-7) || Date.now().toString().slice(-7)}`;
  }

  async function receiptBlob(data, suppliedPhoto = null) {
    const canvas = document.createElement('canvas'); canvas.width = 720; canvas.height = 1220;
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const customer = data.customer || {}; const membership = data.membership || {};
    const summary = data.paymentSummary || membership.payment || {};
    ctx.fillStyle = '#1473d4'; ctx.font = '700 34px Arial'; ctx.fillText('GRAVITY FITNESS UNISEX GYM', 44, 60);
    ctx.fillStyle = '#222'; ctx.font = '25px Arial'; ctx.fillText('+91 79995 26112', 44, 102);
    ctx.font = '700 25px Arial'; ctx.fillText(`Receipt No. ${receiptNumber(data)}`, 44, 150);
    drawLine(ctx, 184);
    const photoBlob = suppliedPhoto || await fetchPhoto(customer.id).catch(() => null);
    const photo = await blobToImage(photoBlob).catch(() => null);
    if (photo) {
      const size = 122; const x = 50; const y = 220;
      const ratio = Math.max(size / photo.width, size / photo.height);
      const sw = size / ratio; const sh = size / ratio; const sx = (photo.width - sw) / 2; const sy = (photo.height - sh) / 2;
      ctx.save(); ctx.beginPath(); ctx.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2); ctx.clip();
      ctx.drawImage(photo, sx, sy, sw, sh, x, y, size, size); ctx.restore();
      if (typeof photo.close === 'function') photo.close(); if (photo._gravityUrl) URL.revokeObjectURL(photo._gravityUrl);
    }
    ctx.fillStyle = '#222'; ctx.font = '700 34px Arial'; ctx.fillText(customer.displayName || 'Member', 205, 250);
    ctx.font = '24px Arial'; ctx.fillText(`Member id : ${membership.membershipNumber || '--'}`, 205, 292);
    ctx.fillText(customer.phone || '--', 205, 330);
    ctx.fillStyle = '#777'; ctx.fillText(`Joined : ${formatDate(customer.joinedAt || membership.startsAt)}`, 205, 368);
    drawLine(ctx, 410);
    pair(ctx, 'Purchase date', formatDate(data.payment?.paidAt || data.createdAt || Math.floor(Date.now() / 1000)), 462);
    pair(ctx, 'Plan name', membership.planName || '--', 514);
    pair(ctx, 'Start date', formatDate(membership.startsAt), 566);
    pair(ctx, 'Expire date', formatDate(membership.endsAt), 618);
    drawLine(ctx, 660);
    pair(ctx, 'Admission fee', money(0), 718);
    pair(ctx, 'Fees', money(summary.totalPaise ?? membership.pricePaise ?? 0), 770);
    pair(ctx, 'Discount', money(0), 822);
    drawLine(ctx, 856);
    pair(ctx, 'Final amount', money(summary.totalPaise ?? membership.pricePaise ?? 0), 918, true);
    pair(ctx, 'Total paid amount', money(summary.paidPaise ?? 0), 970);
    pair(ctx, 'Total Unpaid amount', money(summary.pendingPaise ?? 0), 1022);
    drawLine(ctx, 1060);
    ctx.fillStyle = '#d32f2f'; ctx.font = '700 21px Arial'; ctx.textAlign = 'center';
    ctx.fillText('Fees are fixed, non-refundable, and must be paid on time.', 360, 1110);
    ctx.fillStyle = '#222'; ctx.font = '700 22px Arial'; ctx.fillText('CONTACT - 7999526112', 360, 1155); ctx.textAlign = 'left';
    return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('Could not create receipt image.')), 'image/jpeg', 0.92));
  }

  async function shareReceipt(data, photoBlob = null) {
    const blob = await receiptBlob(data, photoBlob);
    const membership = data.membership || {}; const customer = data.customer || {};
    const safe = String(membership.membershipNumber || customer.displayName || 'member').replace(/[^a-z0-9_-]+/gi, '-');
    const file = new File([blob], `gravity-receipt-${safe}.jpg`, { type: 'image/jpeg' });
    const text = `Gravity Fitness receipt for ${customer.displayName || 'member'} - ${membership.planName || 'membership'}.`;
    if (navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
      await navigator.share({ title: 'Gravity Fitness Receipt', text, files: [file] });
      return;
    }
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = file.name; document.body.appendChild(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    const phone = phoneDigits(customer.phone);
    if (phone) window.open(`https://wa.me/${phone}?text=${encodeURIComponent(text + ' Receipt image has been downloaded; attach it here.')}`, '_blank', 'noopener');
    core()?.flash('Receipt downloaded. Attach the image in WhatsApp.', 'ok');
  }

  function fromDetail(detail) {
    const items = detail?.membership?.all || [];
    const membership = detail?.membership?.current || detail?.membership?.upcoming || items.find((item) => item.status === 'expired') || null;
    if (!detail?.customer || !membership) throw new Error('No membership receipt is available for this person.');
    return { customer: detail.customer, membership, paymentSummary: membership.payment || {} };
  }

  window.GravityReceiptAdmin = { preparePhoto, uploadPhoto, shareReceipt, fromDetail };
})();
