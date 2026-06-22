(function () {
  function fillSelect(select, items, placeholder, valueKey, labelKey) {
    if (!select) return;
    const prev = select.value;
    select.innerHTML = `<option value="">${placeholder}</option>`;
    items.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = String(item[valueKey]);
      opt.textContent = item[labelKey];
      select.appendChild(opt);
    });
    if (prev && Array.from(select.options).some((o) => o.value === prev)) {
      select.value = prev;
    }
  }

  function setupCascadeForm(config) {
    const modal = document.getElementById(config.modalId);
    if (!modal) return;

    const form = document.getElementById(config.formId);
    const managerSel = config.managerId
      ? document.getElementById(config.managerId)
      : null;
    const managerPick = Boolean(config.managerPick && managerSel);
    const regionSel = document.getElementById(config.regionId);
    const clientSel = document.getElementById(config.clientId);
    const brandSel = config.brandId ? document.getElementById(config.brandId) : null;
    const errEl = document.getElementById(config.errorId);
    const openBtn = document.querySelector(config.openSelector);

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

    function managerQuery() {
      if (!managerPick || !managerSel || !managerSel.value) return "";
      return `&manager_id=${encodeURIComponent(managerSel.value)}`;
    }

    function resetRegions() {
      if (!regionSel) return;
      fillSelect(
        regionSel,
        [],
        managerPick ? "Спочатку оберіть менеджера" : "Завантаження…",
        "id",
        "name"
      );
      regionSel.disabled = managerPick;
    }

    function resetClients() {
      if (!clientSel) return;
      fillSelect(clientSel, [], "Спочатку оберіть область", "id", "name");
      clientSel.disabled = true;
    }

    function resetBrands() {
      if (!brandSel) return;
      fillSelect(brandSel, [], "Спочатку оберіть клієнта", "id", "name");
      brandSel.disabled = true;
    }

    function openModal() {
      modal.hidden = false;
      document.body.classList.add("modal-open");
      showError("");
      if (managerPick) {
        if (managerSel && managerSel.value) {
          loadRegions();
        } else {
          resetRegions();
          resetClients();
          if (brandSel) resetBrands();
        }
      } else {
        loadRegions();
      }
    }

    function closeModal() {
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      if (form) form.reset();
      resetRegions();
      resetClients();
      if (brandSel) resetBrands();
    }

    async function fetchJson(url) {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Помилка завантаження");
      }
      return res.json();
    }

    async function loadRegions() {
      if (!regionSel) return;
      if (managerPick && (!managerSel || !managerSel.value)) {
        resetRegions();
        resetClients();
        if (brandSel) resetBrands();
        return;
      }

      regionSel.disabled = true;
      fillSelect(regionSel, [], "Завантаження…", "id", "name");
      try {
        const url = managerPick
          ? `/api/form/regions?manager_id=${encodeURIComponent(managerSel.value)}`
          : "/api/form/regions";
        const regions = await fetchJson(url);
        fillSelect(regionSel, regions, "Оберіть область", "id", "name");
        regionSel.disabled = regions.length === 0;
        resetClients();
        if (brandSel) resetBrands();
        if (regions.length === 0) {
          showError("Немає областей для обраного менеджера");
        } else {
          showError("");
        }
      } catch (e) {
        showError(e.message || "Не вдалося завантажити області");
        fillSelect(regionSel, [], "Помилка", "id", "name");
      }
    }

    async function loadClients(regionId) {
      if (!clientSel) return;
      resetClients();
      if (brandSel) resetBrands();
      if (!regionId) return;
      if (managerPick && (!managerSel || !managerSel.value)) return;

      clientSel.disabled = true;
      fillSelect(clientSel, [], "Завантаження…", "id", "name");
      try {
        const clients = await fetchJson(
          `/api/form/clients?region_id=${encodeURIComponent(regionId)}${managerQuery()}`
        );
        fillSelect(clientSel, clients, "Оберіть клієнта", "id", "name");
        clientSel.disabled = clients.length === 0;
        if (clients.length === 0) {
          showError("У цій області немає клієнтів");
        } else {
          showError("");
        }
      } catch (e) {
        showError(e.message || "Не вдалося завантажити клієнтів");
      }
    }

    async function loadBrands(clientId) {
      if (!brandSel) return;
      resetBrands();
      if (!clientId) return;

      brandSel.disabled = true;
      fillSelect(brandSel, [], "Завантаження…", "id", "name");
      try {
        const brands = await fetchJson(
          `/api/form/brands?client_id=${encodeURIComponent(clientId)}${managerQuery()}`
        );
        fillSelect(brandSel, brands, "Оберіть марку", "id", "name");
        brandSel.disabled = brands.length === 0;
        if (brands.length === 0) {
          showError("У клієнта немає стендів з відомими брендами");
        } else {
          showError("");
        }
      } catch (e) {
        showError(e.message || "Не вдалося завантажити бренди");
      }
    }

    if (openBtn) {
      openBtn.addEventListener("click", openModal);
    }

    modal.querySelectorAll("[data-close-modal]").forEach((el) => {
      el.addEventListener("click", closeModal);
    });

    if (managerSel) {
      managerSel.addEventListener("change", () => {
        showError("");
        loadRegions();
      });
    }

    if (regionSel) {
      regionSel.addEventListener("change", () => {
        showError("");
        loadClients(regionSel.value);
      });
    }

    if (clientSel) {
      clientSel.addEventListener("change", () => {
        showError("");
        if (brandSel) {
          loadBrands(clientSel.value);
        }
      });
    }

    if (form && config.regionFieldName) {
      form.addEventListener("submit", (ev) => {
        if (!regionSel || !regionSel.value) {
          ev.preventDefault();
          showError("Оберіть область");
        }
      });
    }
  }

  window.setupCascadeForm = setupCascadeForm;
})();
