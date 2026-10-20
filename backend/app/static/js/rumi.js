/**
 * Rumi Dental Care — Client-side API helper, Toast Notification system,
 * Appointment Slot Loader, and Interactive FDI Dental Chart Controller.
 */

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : '';
}

function showToast(message, type = 'success') {
  let container = document.getElementById('rumi-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'rumi-toast-container';
    container.className = 'fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  const bg = type === 'error'
    ? 'bg-red-600 text-white'
    : type === 'warning'
    ? 'bg-amber-500 text-white'
    : 'bg-[#01578c] text-white';
  el.className = `${bg} px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center justify-between gap-3 transition-all`;
  el.setAttribute('role', 'status');
  const msgSpan = document.createElement('span');
  msgSpan.textContent = String(message || '');
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'opacity-80 hover:opacity-100 font-bold';
  closeBtn.textContent = '×';
  closeBtn.onclick = () => el.remove();
  el.appendChild(msgSpan);
  el.appendChild(closeBtn);
  container.appendChild(el);
  setTimeout(() => {
    if (el && el.parentElement) el.remove();
  }, 4500);
}

async function rumiApi(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const csrf = getCookie('rumi_csrf_token') || (window.RUMI_CSRF_TOKEN || '');
  if (csrf) {
    headers['X-CSRF-Token'] = csrf;
  }
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch(url, Object.assign({}, options, { headers, credentials: 'same-origin' }));
  let data = null;
  const contentType = resp.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    data = await resp.json();
  } else {
    data = await resp.text();
  }
  if (!resp.ok) {
    const detail = (data && data.detail)
      ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      : `Request failed with status ${resp.status}`;
    throw new Error(detail);
  }
  return data;
}

async function handleLogout() {
  try {
    await rumiApi('/api/v1/auth/logout', { method: 'POST', body: JSON.stringify({}) });
  } catch (e) {
    // Redirect regardless
  }
  window.location.href = '/login';
}

async function markAllNotificationsRead() {
  try {
    await rumiApi('/api/v1/notifications/read-all', { method: 'POST', body: JSON.stringify({}) });
    showToast('All notifications marked as read.');
    setTimeout(() => window.location.reload(), 500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadAvailableTimeSlots(doctorSelectId, dateInputId, serviceSelectId, targetSelectId) {
  const docEl = document.getElementById(doctorSelectId);
  const dateEl = document.getElementById(dateInputId);
  const srvEl = serviceSelectId ? document.getElementById(serviceSelectId) : null;
  const slotEl = document.getElementById(targetSelectId);
  if (!docEl || !dateEl || !slotEl || !docEl.value || !dateEl.value) return;

  try {
    const srvParam = (srvEl && srvEl.value) ? `&service_id=${encodeURIComponent(srvEl.value)}` : '';
    const res = await rumiApi(
      `/api/v1/appointments/available-slots?doctor_id=${encodeURIComponent(docEl.value)}&appointment_date=${encodeURIComponent(dateEl.value)}${srvParam}`
    );
    slotEl.innerHTML = '';
    const available = (res.slots || []).filter(s => s.is_available);
    if (available.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No available slots on selected date (Sunday closed / booked)';
      slotEl.appendChild(opt);
      return;
    }
    available.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.start_time;
      opt.textContent = `${s.start_time} – ${s.end_time} (Available)`;
      slotEl.appendChild(opt);
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}
