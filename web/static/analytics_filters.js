(function () {
  const LOADING_CLASS = "is-loading";

  function showPeriodRowLoading(select) {
    const row = select.closest(".filters-period-row");
    if (!row) return;
    row.classList.add(LOADING_CLASS);
    row.setAttribute("aria-busy", "true");
  }

  function bindPeriodAutoSubmit(select) {
    select.addEventListener("change", () => {
      const form = select.form;
      if (!form) return;
      showPeriodRowLoading(select);
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });
  }

  document
    .querySelectorAll('select[name="period_kind"], select[name="compare_kind"]')
    .forEach(bindPeriodAutoSubmit);
})();
