(function () {
  const modal = document.getElementById("stand-move-modal");
  if (!modal) return;

  const form = document.getElementById("stand-move-form");
  const operationSel = document.getElementById("move-operation");
  const operationLabel = document.getElementById("move-operation-label");
  const fromLabel = document.getElementById("move-from-label");
  const fromSel = document.getElementById("move-from");
  const standSel = document.getElementById("move-stand");
  const kindSel = document.getElementById("move-target-kind");
  const recipientBlock = document.getElementById("move-recipient-block");
  const writeoffBlock = document.getElementById("move-writeoff-block");
  const existingBlock = document.getElementById("move-existing-block");
  const newBlock = document.getElementById("move-new-block");
  const qtyInput = document.getElementById("move-qty");
  const submitBtn = document.getElementById("move-submit-btn");
  const titleEl = document.getElementById("stand-move-title");
  const hintEl = document.getElementById("move-hint");
  const errEl = document.getElementById("move-error");
  const managerIdInput = document.getElementById("warehouse-manager-id");

  const standsJsonEl = document.getElementById("client-stands-json");
  const warehouseJsonEl = document.getElementById("warehouse-stands-json");
  let clientStandsMap = {};
  let warehouseStands = [];

  if (standsJsonEl) {
    try {
      clientStandsMap = JSON.parse(standsJsonEl.textContent || "{}");
    } catch (_) {
      clientStandsMap = {};
    }
  }
  if (warehouseJsonEl) {
    try {
      warehouseStands = JSON.parse(warehouseJsonEl.textContent || "[]");
    } catch (_) {
      warehouseStands = [];
    }
  }

  const allStandOptions = standSel
    ? Array.from(standSel.options)
        .filter((opt) => opt.value)
        .map((opt) => ({ id: opt.value, name: opt.textContent }))
    : [];

  function setRecipientEnabled(enabled) {
    if (!recipientBlock) return;
    recipientBlock.querySelectorAll("select, input").forEach((el) => {
      el.disabled = !enabled;
    });
  }

  function fillStandOptions(source, emptyLabel) {
    if (!standSel) return;
    const prev = standSel.value;
    standSel.innerHTML = `<option value="">${emptyLabel}</option>`;
    source.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = String(item.id);
      opt.textContent = item.qty ? `${item.name} (${item.qty} шт)` : item.name;
      if (item.qty) opt.dataset.qty = String(item.qty);
      standSel.appendChild(opt);
    });
    if (prev && Array.from(standSel.options).some((o) => o.value === prev)) {
      standSel.value = prev;
    }
  }

  function refreshClientStandOptions() {
    if (!fromSel) return;
    const clientId = fromSel.value;
    const items = clientStandsMap[clientId] || [];
    fillStandOptions(
      items.length ? items : allStandOptions,
      "Оберіть стенд"
    );
    syncQtyLimit();
  }

  function refreshWarehouseStandOptions() {
    fillStandOptions(warehouseStands, "Оберіть стенд зі складу");
    syncQtyLimit();
  }

  function syncQtyLimit() {
    if (!qtyInput || !standSel) return;
    const op = operationSel ? operationSel.value : "move";
    const selected = standSel.selectedOptions[0];
    const maxQty = selected && selected.dataset.qty ? parseInt(selected.dataset.qty, 10) : null;
    if ((op === "write_off" || op === "to_warehouse") && maxQty) {
      qtyInput.max = String(maxQty);
      if (parseInt(qtyInput.value, 10) > maxQty) qtyInput.value = String(maxQty);
    } else if (op === "move" || op === "from_warehouse") {
      qtyInput.max = "1";
      qtyInput.value = "1";
    } else {
      qtyInput.removeAttribute("max");
    }
  }

  function openModal(operation) {
    if (operation && operationSel) {
      operationSel.value = operation;
    }
    syncOperationUi();
    modal.hidden = false;
    document.body.classList.add("modal-open");
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = "";
    }
  }

  document.querySelectorAll("[data-open-stand-move]").forEach((btn) => {
    btn.addEventListener("click", () => openModal("move"));
  });
  document.querySelectorAll("[data-open-stand-writeoff]").forEach((btn) => {
    btn.addEventListener("click", () => openModal("write_off"));
  });
  document.querySelectorAll("[data-open-stand-to-warehouse]").forEach((btn) => {
    btn.addEventListener("click", () => openModal("to_warehouse"));
  });
  document.querySelectorAll("[data-open-stand-from-warehouse]").forEach((btn) => {
    btn.addEventListener("click", () => openModal("from_warehouse"));
  });

  modal.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  function toggleTargetBlocks() {
    if (!kindSel || !existingBlock || !newBlock) return;
    const isNew = kindSel.value === "new";
    existingBlock.hidden = isNew;
    newBlock.hidden = !isNew;
  }

  function syncOperationUi() {
    const op = operationSel ? operationSel.value : "move";
    const isWriteOff = op === "write_off";
    const isToWarehouse = op === "to_warehouse";
    const isFromWarehouse = op === "from_warehouse";
    const isMove = op === "move";

    if (operationLabel) operationLabel.hidden = false;
    if (fromLabel) fromLabel.hidden = isFromWarehouse;
    if (fromSel) {
      fromSel.hidden = isFromWarehouse;
      fromSel.required = !isFromWarehouse;
      fromSel.disabled = isFromWarehouse;
    }

    if (recipientBlock) recipientBlock.hidden = isWriteOff || isToWarehouse;
    if (writeoffBlock) writeoffBlock.hidden = !(isWriteOff || isToWarehouse);
    setRecipientEnabled(isMove || isFromWarehouse);

    if (titleEl) {
      const titles = {
        move: "Перемістити стенд",
        write_off: "Списати стенд",
        to_warehouse: "Повернути на склад",
        from_warehouse: "Встановити зі складу",
      };
      titleEl.textContent = titles[op] || "Операція зі стендом";
    }
    if (hintEl) {
      const hints = {
        move: "Знімає стенд у відправника й додає отримувачу. Отримувач може бути існуючим клієнтом або новим (у того ж менеджера).",
        write_off: "Знімає стенд з торгової точки. Він більше не враховується в аналітиці; запис зʼявиться в історії як списання.",
        to_warehouse: "Знімає стенд з ТТ і повертає на ваш віртуальний склад. В аналітиці встановлених не рахується.",
        from_warehouse: "Бере стенд зі складу й встановлює на торгову точку. Зʼявиться в аналітиці встановлених.",
      };
      hintEl.textContent = hints[op] || "";
    }
    if (submitBtn) {
      const labels = {
        move: "Перемістити",
        write_off: "Списати",
        to_warehouse: "На склад",
        from_warehouse: "Встановити",
      };
      submitBtn.textContent = labels[op] || "Виконати";
      submitBtn.classList.toggle("btn-danger", isWriteOff);
      submitBtn.classList.toggle("btn-primary", !isWriteOff);
    }

    if (isFromWarehouse) {
      refreshWarehouseStandOptions();
    } else {
      refreshClientStandOptions();
    }
    syncQtyLimit();
    if (isMove || isFromWarehouse) {
      toggleTargetBlocks();
    }
  }

  if (kindSel) kindSel.addEventListener("change", toggleTargetBlocks);
  if (operationSel) operationSel.addEventListener("change", syncOperationUi);
  if (fromSel) fromSel.addEventListener("change", refreshClientStandOptions);
  if (standSel) standSel.addEventListener("change", syncQtyLimit);
  syncOperationUi();

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = "";
    }
    const op = operationSel ? operationSel.value : "move";
    const urls = {
      move: "/stands/move",
      write_off: "/stands/write-off",
      to_warehouse: "/stands/to-warehouse",
      from_warehouse: "/stands/from-warehouse",
    };
    const url = urls[op];
    if (!url) return;

    const fd = new FormData(form);
    if (op === "write_off" || op === "to_warehouse") {
      fd.delete("to_kind");
      fd.delete("to_client_id");
      fd.delete("new_name");
      fd.delete("new_address");
      fd.delete("new_city");
      fd.delete("new_oblast");
    }
    if (op !== "from_warehouse") {
      fd.delete("manager_id");
    }
    if (op === "from_warehouse" && managerIdInput && !fd.get("manager_id")) {
      fd.set("manager_id", managerIdInput.value);
    }

    try {
      const res = await fetch(url, { method: "POST", body: fd });
      let data = {};
      try {
        data = await res.json();
      } catch (_) {
        throw new Error("Помилка сервера");
      }
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Помилка операції");
      }
      window.location.reload();
    } catch (err) {
      if (errEl) {
        errEl.textContent = err.message || "Помилка";
        errEl.hidden = false;
      }
    }
  });
})();
