(() => {
  const root = document.getElementById("tm-root");
  if (!root) return;

  const statusUrl = root.dataset.statusUrl || "/tasks/status";

  document.querySelectorAll("[data-open-create]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = document.getElementById("tm-create-modal");
      const statusInput = document.getElementById("tm-create-status");
      if (statusInput) statusInput.value = btn.dataset.status || "new";
      if (!modal) return;
      modal.hidden = false;
      document.body.classList.add("modal-open");
    });
  });

  document.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", () => {
      const modal = el.closest(".modal");
      if (!modal) return;
      modal.hidden = true;
      document.body.classList.remove("modal-open");
    });
  });

  const filters = document.getElementById("tm-filters");
  const filtersToggle = document.querySelector("[data-open-filters]");
  if (filters && filtersToggle) {
    filtersToggle.addEventListener("click", () => {
      filters.classList.toggle("is-open");
    });
  }

  document.querySelectorAll("[data-tm-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tmTab;
      document.querySelectorAll("[data-tm-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
      document.querySelectorAll("[data-tm-panel]").forEach((panel) => {
        const on = panel.dataset.tmPanel === tab;
        panel.classList.toggle("is-active", on);
        panel.hidden = !on;
      });
    });
  });

  let draggedId = null;

  document.querySelectorAll(".tm-card[draggable='true']").forEach((card) => {
    card.addEventListener("dragstart", () => {
      draggedId = card.dataset.taskId;
    });
  });

  document.querySelectorAll("[data-drop-status]").forEach((col) => {
    col.addEventListener("dragover", (event) => {
      event.preventDefault();
      col.classList.add("is-drop");
    });
    col.addEventListener("dragleave", () => col.classList.remove("is-drop"));
    col.addEventListener("drop", async (event) => {
      event.preventDefault();
      col.classList.remove("is-drop");
      if (!draggedId) return;
      const body = new FormData();
      body.set("task_id", draggedId);
      body.set("status", col.dataset.dropStatus);
      body.set("return_view", "board");
      try {
        await fetch(statusUrl, { method: "POST", body, credentials: "same-origin" });
        window.location.reload();
      } catch (err) {
        console.error(err);
      }
    });
  });
})();
