document.addEventListener("DOMContentLoaded", function () {
  // Theme toggle (persisted)
  var root = document.documentElement;
  var themeBtn = document.getElementById("themeToggle");
  var saved = localStorage.getItem("sas-theme");
  if (saved) root.setAttribute("data-theme", saved);
  updateThemeIcon();

  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var current = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", current);
      localStorage.setItem("sas-theme", current);
      updateThemeIcon();
    });
  }

  function updateThemeIcon() {
    if (!themeBtn) return;
    var isDark = root.getAttribute("data-theme") === "dark";
    themeBtn.innerHTML = isDark
      ? '<i class="fa-solid fa-sun"></i>'
      : '<i class="fa-solid fa-moon"></i>';
  }

  // Mobile sidebar toggle
  var sidebar = document.getElementById("sidebar");
  var sidebarToggle = document.getElementById("sidebarToggle");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("sidebar--open");
    });
  }

  // Roster search filter (roll call page)
  var rosterSearch = document.getElementById("rosterSearch");
  if (rosterSearch) {
    rosterSearch.addEventListener("input", function () {
      var term = rosterSearch.value.toLowerCase();
      document.querySelectorAll(".roster-row").forEach(function (row) {
        var name = row.getAttribute("data-name") || "";
        row.style.display = name.indexOf(term) !== -1 ? "" : "none";
      });
    });
  }

  // Auto-dismiss flash messages, except ones containing a password
  document.querySelectorAll(".flash").forEach(function (el) {
    if (el.textContent.toLowerCase().includes("password")) {
      return; // leave it on screen until manually closed
    }
    setTimeout(function () {
      el.style.transition = "opacity 300ms ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 320);
    }, 5000);
  });

  // Manual close button on flash messages
  document.querySelectorAll(".flash-close").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var el = btn.closest(".flash");
      el.style.transition = "opacity 300ms ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 320);
    });
  });
});