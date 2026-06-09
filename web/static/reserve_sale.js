(function () {
  const modal = document.getElementById("reserve-sale-modal");
  if (!modal) return;

  const form = document.getElementById("reserve-sale-form");
  const reserveIdInput = document.getElementById("reserve-sale-id");
  const metaEl = document.getElementById("reserve-sale-meta");
  const brandSel = document.getElementById("reserve-sale-brand");
  const qtyInput = document.getElementById("reserve-sale-quantity");
  const errEl = document.getElementById("reserve-sale-error");

  function showError(msg) {
    if (!errEl) return;
    if (msg) {
      errEl.textContent = msg;
      errEl.hidden = false;
    } else {
      errEl.textContent = "";
      errEl.hidden = true;
    }
  }

  function fillBrands(brands) {
    if (!brandSel) return;
    brandSel.innerHTML = '<option value="">Оберіть марку</option>';
    brands.forEach((b) => {
      const opt = document.createElement("option");
      opt.value = String(b.id);
      opt.textContent = b.name;
      brandSel.appendChild(opt);
    });
    brandSel.disabled = brands.length === 0;
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (form) form.reset();
    if (brandSel) {
      brandSel.innerHTML = '<option value="">—</option>';
      brandSel.disabled = true;
    }
    showError("");
  }

  async function openModal(reserveId) {
    modal.hidden = false;
    document.body.classList.add("modal-open");
    showError("");
    if (reserveIdInput) reserveIdInput.value = String(reserveId);
    if (brandSel) {
      brandSel.disabled = true;
      brandSel.innerHTML = '<option value="">Завантаження…</option>';
    }
    if (qtyInput) qtyInput.value = "";

    try {
      const res = await fetch(`/api/reserves/${reserveId}/brands`, {
        credentials: "same-origin",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Помилка завантаження");
      }
      const data = await res.json();
      if (metaEl) {
        metaEl.textContent = `${data.client_name} · резерв #${data.reserve_id} · ${data.material} — ${data.reserve_qty} кв. м`;
      }
      fillBrands(data.brands || []);
      if (!data.brands || data.brands.length === 0) {
        showError("У клієнта немає стендів з відомими брендами");
      }
    } catch (e) {
      showError(e.message || "Не вдалося завантажити дані резерву");
      if (brandSel) {
        brandSel.innerHTML = '<option value="">Помилка</option>';
      }
    }
  }

  document.querySelectorAll("[data-open-reserve-sale]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-reserve-id");
      if (id) openModal(id);
    });
  });

  modal.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });
})();
