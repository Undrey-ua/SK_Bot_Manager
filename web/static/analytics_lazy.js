(function () {
  function loadPartial(buttonId, containerId) {
    const btn = document.getElementById(buttonId);
    const container = document.getElementById(containerId);
    if (!btn || !container || btn.disabled) return;

    const url = btn.getAttribute("data-url");
    if (!url) return;

    btn.disabled = true;
    btn.textContent = "Завантаження…";
    container.innerHTML = '<p class="muted">Завантаження…</p>';

    fetch(url, { credentials: "same-origin" })
      .then((res) => {
        if (!res.ok) throw new Error("Помилка завантаження");
        return res.text();
      })
      .then((html) => {
        container.innerHTML = html;
        btn.hidden = true;
        const wrap = btn.closest(".lazy-load-actions");
        if (wrap) wrap.hidden = true;
      })
      .catch(() => {
        container.innerHTML =
          '<p class="modal__error">Не вдалося завантажити. Спробуйте ще раз.</p>';
        btn.disabled = false;
        btn.textContent = btn.getAttribute("data-label") || "Завантажити";
      });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const matrixBtn = document.getElementById("load-sales-matrix");
    if (matrixBtn) {
      matrixBtn.addEventListener("click", () =>
        loadPartial("load-sales-matrix", "sales-matrix-container")
      );
    }
    const inactiveBtn = document.getElementById("load-inactive-stands");
    if (inactiveBtn) {
      inactiveBtn.addEventListener("click", () =>
        loadPartial("load-inactive-stands", "inactive-stands-container")
      );
    }
  });
})();
