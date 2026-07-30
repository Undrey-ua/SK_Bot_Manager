(function () {
  const LOCKED = "data-submit-locked";

  function submitButtons(form) {
    return form.querySelectorAll('button[type="submit"], input[type="submit"]');
  }

  function lockFormSubmit(form) {
    if (!(form instanceof HTMLFormElement)) return false;
    if (form.getAttribute(LOCKED) === "1") return false;

    form.setAttribute(LOCKED, "1");
    submitButtons(form).forEach((btn) => {
      if (!btn.dataset.submitLabel) {
        btn.dataset.submitLabel =
          btn.tagName === "INPUT" ? btn.value : (btn.textContent || "").trim();
      }
      btn.disabled = true;
      const loading = btn.dataset.submitLoading || "Збереження…";
      if (btn.tagName === "INPUT") btn.value = loading;
      else btn.textContent = loading;
    });
    return true;
  }

  function unlockFormSubmit(form) {
    if (!(form instanceof HTMLFormElement)) return;
    form.removeAttribute(LOCKED);
    submitButtons(form).forEach((btn) => {
      const label = btn.dataset.submitLabel;
      if (label) {
        if (btn.tagName === "INPUT") btn.value = label;
        else btn.textContent = label;
      }
      btn.disabled = false;
    });
  }

  document.addEventListener(
    "submit",
    (ev) => {
      const form = ev.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.hasAttribute("data-no-submit-guard")) return;

      if (form.getAttribute(LOCKED) === "1") {
        ev.preventDefault();
        ev.stopImmediatePropagation();
      }
    },
    true
  );

  document.addEventListener(
    "submit",
    (ev) => {
      const form = ev.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.hasAttribute("data-no-submit-guard")) return;
      if (ev.defaultPrevented) return;

      lockFormSubmit(form);
    },
    false
  );

  window.lockFormSubmit = lockFormSubmit;
  window.unlockFormSubmit = unlockFormSubmit;
})();
