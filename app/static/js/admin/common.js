document.addEventListener("DOMContentLoaded", () => {
  const toggleButton = document.querySelector("[data-sidebar-toggle]");
  const wrapper = document.getElementById("admin-wrapper");

  if (toggleButton && wrapper) {
    const isCollapsed = localStorage.getItem("sidebar-collapsed") === "true";
    if (isCollapsed) {
      wrapper.classList.add("sidebar-collapsed");
      toggleButton.classList.add("is-active");
    }

    toggleButton.addEventListener("click", () => {
      const isCurrentlyCollapsed = wrapper.classList.contains("sidebar-collapsed");
      if (isCurrentlyCollapsed) {
        wrapper.classList.remove("sidebar-collapsed");
        toggleButton.classList.remove("is-active");
        localStorage.setItem("sidebar-collapsed", "false");
      } else {
        wrapper.classList.add("sidebar-collapsed");
        toggleButton.classList.add("is-active");
        localStorage.setItem("sidebar-collapsed", "true");
      }
    });
  }

  const fullscreenButtons = document.querySelectorAll("[data-fullscreen-toggle]");
  fullscreenButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        if (document.fullscreenElement) {
          await document.exitFullscreen();
        } else {
          await document.documentElement.requestFullscreen();
        }
      } catch (err) {
        console.error("Fullscreen toggle failed:", err);
      }
    });
  });

  if (window.bootstrap) {
    document
      .querySelectorAll('[data-bs-toggle="tooltip"]')
      .forEach((el) => new window.bootstrap.Tooltip(el));

    document
      .querySelectorAll('[data-bs-toggle="popover"]')
      .forEach((el) => new window.bootstrap.Popover(el));
  }
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "k") {
    const target = document.querySelector("[data-search-input]");
    if (target) {
      event.preventDefault();
      target.focus();
    }
  }
});
