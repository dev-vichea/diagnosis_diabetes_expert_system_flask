(() => {
  const findDropdownMenu = (toggle) => {
    if (!toggle) {
      return null;
    }
    const parent = toggle.closest('.dropdown, .dropup, .dropend, .dropstart, .btn-group');
    if (!parent) {
      return null;
    }
    return parent.querySelector('.dropdown-menu');
  };

  const setFallbackState = (toggle, menu, isOpen) => {
    if (!toggle || !menu) {
      return;
    }
    if (isOpen) {
      toggle.dataset.fallbackOpen = 'true';
      menu.dataset.fallbackOpen = 'true';
    } else {
      delete toggle.dataset.fallbackOpen;
      delete menu.dataset.fallbackOpen;
    }
  };

  const openMenu = (toggle, menu) => {
    if (!toggle || !menu) {
      return;
    }
    toggle.setAttribute('aria-expanded', 'true');
    menu.classList.add('show');
    setFallbackState(toggle, menu, true);
  };

  const closeMenu = (toggle, menu) => {
    if (!toggle || !menu) {
      return;
    }
    toggle.setAttribute('aria-expanded', 'false');
    menu.classList.remove('show');
    setFallbackState(toggle, menu, false);
  };

  const initBootstrapDropdowns = () => {
    if (!window.bootstrap || !window.bootstrap.Dropdown) {
      return;
    }
    document.querySelectorAll('[data-bs-toggle="dropdown"]').forEach((el) => {
      if (!bootstrap.Dropdown.getInstance(el)) {
        new bootstrap.Dropdown(el);
      }
    });
  };

  const initFallbackDropdowns = () => {
    const toggles = Array.from(document.querySelectorAll('[data-bs-toggle="dropdown"]'));
    toggles.forEach((toggle) => {
      toggle.addEventListener('click', () => {
        const menu = findDropdownMenu(toggle);
        if (!menu) {
          return;
        }
        setTimeout(() => {
          const isOpen = menu.classList.contains('show');
          const isFallbackOpen = toggle.dataset.fallbackOpen === 'true';
          if (!isOpen && !isFallbackOpen) {
            openMenu(toggle, menu);
          } else if (isOpen && isFallbackOpen) {
            closeMenu(toggle, menu);
          }
        }, 0);
      });
    });

    document.addEventListener('click', (event) => {
      const target = event.target;
      document.querySelectorAll('.dropdown-menu.show[data-fallback-open="true"]').forEach((menu) => {
        const dropdown = menu.closest('.dropdown, .dropup, .dropend, .dropstart, .btn-group');
        if (dropdown && dropdown.contains(target)) {
          return;
        }
        const toggle = dropdown
          ? dropdown.querySelector('[data-bs-toggle="dropdown"]')
          : null;
        closeMenu(toggle, menu);
      });
    });

    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') {
        return;
      }
      document.querySelectorAll('.dropdown-menu.show[data-fallback-open="true"]').forEach((menu) => {
        const dropdown = menu.closest('.dropdown, .dropup, .dropend, .dropstart, .btn-group');
        const toggle = dropdown
          ? dropdown.querySelector('[data-bs-toggle="dropdown"]')
          : null;
        closeMenu(toggle, menu);
      });
    });
  };

  const findCollapseTarget = (toggle) => {
    if (!toggle) {
      return null;
    }
    const selector = toggle.getAttribute('data-bs-target') || toggle.getAttribute('href');
    if (!selector || !selector.startsWith('#')) {
      return null;
    }
    return document.querySelector(selector);
  };

  const isSidebarCollapseToggle = (toggle) => {
    if (!toggle) {
      return false;
    }
    return Boolean(toggle.closest('.admin-sidebar'));
  };

  const syncCollapseToggleState = (toggle, target, isOpen) => {
    if (!toggle || !target) {
      return;
    }
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    if (isSidebarCollapseToggle(toggle)) {
      if (isOpen) {
        toggle.classList.add('active');
      } else {
        toggle.classList.remove('active');
      }
    }
  };

  const initBootstrapCollapses = () => {
    if (!window.bootstrap || !window.bootstrap.Collapse) {
      return;
    }
    document.querySelectorAll('[data-bs-toggle="collapse"]').forEach((toggle) => {
      const target = findCollapseTarget(toggle);
      if (!target) {
        return;
      }
      if (!bootstrap.Collapse.getInstance(target)) {
        new bootstrap.Collapse(target, { toggle: false });
      }
      syncCollapseToggleState(toggle, target, target.classList.contains('show'));
      target.addEventListener('shown.bs.collapse', () => {
        syncCollapseToggleState(toggle, target, true);
      });
      target.addEventListener('hidden.bs.collapse', () => {
        syncCollapseToggleState(toggle, target, false);
      });
    });
  };

  const initFallbackCollapses = () => {
    if (window.bootstrap && window.bootstrap.Collapse) {
      return;
    }
    document.querySelectorAll('[data-bs-toggle="collapse"]').forEach((toggle) => {
      toggle.addEventListener('click', (event) => {
        const target = findCollapseTarget(toggle);
        if (!target) {
          return;
        }
        event.preventDefault();
        const isOpen = target.classList.contains('show');
        if (isOpen) {
          target.classList.remove('show');
          syncCollapseToggleState(toggle, target, false);
        } else {
          target.classList.add('show');
          syncCollapseToggleState(toggle, target, true);
        }
      });
      const target = findCollapseTarget(toggle);
      if (target) {
        syncCollapseToggleState(toggle, target, target.classList.contains('show'));
      }
    });
  };

  const initSidebarCollapses = () => {
    document.querySelectorAll('.admin-sidebar [data-bs-toggle="collapse"]').forEach((toggle) => {
      if (toggle.dataset.sidebarCollapseBound === 'true') {
        return;
      }
      toggle.dataset.sidebarCollapseBound = 'true';
      toggle.addEventListener('click', (event) => {
        const target = findCollapseTarget(toggle);
        if (!target) {
          return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        const isOpen = target.classList.contains('show');
        if (window.bootstrap && window.bootstrap.Collapse) {
          const instance = bootstrap.Collapse.getOrCreateInstance(target, { toggle: false });
          instance.toggle();
        } else {
          target.classList.toggle('show', !isOpen);
          syncCollapseToggleState(toggle, target, !isOpen);
        }
      });
    });
  };

  const init = () => {
    initBootstrapDropdowns();
    initFallbackDropdowns();
    initBootstrapCollapses();
    initFallbackCollapses();
    initSidebarCollapses();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
