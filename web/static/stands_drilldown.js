(function () {
  const modal = document.getElementById("stands-clients-modal");
  const body = document.getElementById("stands-clients-body");
  const titleEl = document.getElementById("stands-clients-title");
  const pdfLink = document.getElementById("stands-clients-pdf");
  if (!modal || !body) return;

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
  }

  function filterParams() {
    const params = new URLSearchParams(window.location.search);
    return params;
  }

  function buildQuery(btn) {
    const params = filterParams();
    params.set("bucket", btn.getAttribute("data-bucket") || "");
    const keys = [
      ["manager", "manager"],
      ["stand", "stand"],
      ["city", "city_detail"],
      ["oblast", "oblast"],
    ];
    keys.forEach(([attr, param]) => {
      const value = btn.getAttribute(`data-${attr}`);
      if (value) {
        params.set(param, value);
      } else {
        params.delete(param);
      }
    });
    return params;
  }

  async function openFromButton(btn) {
    const params = buildQuery(btn);
    const title = btn.getAttribute("data-title");
    if (titleEl && title) titleEl.textContent = title;
    if (pdfLink) {
      pdfLink.href = `/analytics/stands-clients.pdf?${params.toString()}`;
    }
    body.innerHTML = '<p class="muted">Завантаження…</p>';
    modal.hidden = false;
    document.body.classList.add("modal-open");
    try {
      const res = await fetch(`/analytics/partials/stands-clients?${params.toString()}`, {
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("Помилка завантаження");
      body.innerHTML = await res.text();
    } catch (_) {
      body.innerHTML = '<p class="modal__error">Не вдалося завантажити список торгових точок.</p>';
    }
  }

  document.querySelectorAll(".stands-count-link").forEach((btn) => {
    btn.addEventListener("click", () => openFromButton(btn));
  });

  modal.querySelectorAll("[data-close-stands-modal]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });
})();
