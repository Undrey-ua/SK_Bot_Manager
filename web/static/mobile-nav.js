(function () {
  const toggle = document.getElementById("nav-toggle");
  const layout = document.querySelector(".layout");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!toggle || !layout) return;

  function setOpen(open) {
    layout.classList.toggle("nav-open", open);
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) backdrop.hidden = !open;
  }

  toggle.addEventListener("click", function () {
    setOpen(!layout.classList.contains("nav-open"));
  });

  if (backdrop) {
    backdrop.addEventListener("click", function () {
      setOpen(false);
    });
  }

  layout.querySelectorAll(".sidebar a").forEach(function (link) {
    link.addEventListener("click", function () {
      setOpen(false);
    });
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 768) setOpen(false);
  });
})();
