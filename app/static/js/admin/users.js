const ROLE_PRIORITY = ["ADMIN", "KB_DOCTOR", "USER"];
const ROLE_LABELS = {
  admin: "Admin",
  user: "User",
  kb_doctor: "KB Doctor",
};

const DEFAULT_AVATAR = "/assets/images/avatar-placeholder.svg";

function showAlert(message, type = "info", title = "") {
  if (window.Swal) {
    const iconMap = {
      success: "success",
      error: "error",
      warning: "warning",
      info: "info",
    };
    return window.Swal.fire({
      title: title || "Notice",
      text: message,
      icon: iconMap[type] || "info",
      confirmButtonText: "OK",
    });
  }
  alert(message);
  return Promise.resolve();
}

async function confirmDialog(message, options = {}) {
  if (window.Swal) {
    const result = await window.Swal.fire({
      title: options.title || "Are you sure?",
      text: message,
      icon: options.icon || "warning",
      showCancelButton: true,
      confirmButtonText: options.confirmText || "Yes",
      cancelButtonText: options.cancelText || "Cancel",
      confirmButtonColor: options.confirmColor || undefined,
      cancelButtonColor: options.cancelColor || undefined,
    });
    return result.isConfirmed;
  }
  return confirm(message);
}

function getMetaContent(name, fallback = "") {
  const meta = document.querySelector(`meta[name="${name}"]`);
  if (!meta) {
    return fallback;
  }
  const value = meta.getAttribute("content");
  return value || fallback;
}

function normalizeRoles(roles) {
  if (!Array.isArray(roles)) {
    return [];
  }
  return roles
    .map((role) => String(role || "").toUpperCase())
    .filter((role) => role);
}

function pickPrimaryRole(roles) {
  const normalized = normalizeRoles(roles);
  for (const candidate of ROLE_PRIORITY) {
    if (normalized.includes(candidate)) {
      return candidate;
    }
  }
  return normalized[0] || "USER";
}

function roleToUi(role) {
  return String(role || "USER").toLowerCase();
}

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
}

function roleToApi(role) {
  return String(role || "user").toUpperCase();
}

function statusToUi(status) {
  return status === "DISABLED" ? "inactive" : "active";
}

function statusToApi(status) {
  return status === "inactive" ? "DISABLED" : "ACTIVE";
}

function dateOnly(value) {
  if (!value) {
    return "";
  }
  return String(value).split("T")[0];
}

function formatRelativeTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "just now";
  }

  const diffMs = Date.now() - date.getTime();
  const future = diffMs < 0;
  const absMs = Math.abs(diffMs);
  const minutes = Math.floor(absMs / (1000 * 60));
  const hours = Math.floor(absMs / (1000 * 60 * 60));
  const days = Math.floor(absMs / (1000 * 60 * 60 * 24));

  const suffix = future ? "from now" : "ago";
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? "" : "s"} ${suffix}`;
  }
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? "" : "s"} ${suffix}`;
  }
  if (days < 7) {
    return `${days} day${days === 1 ? "" : "s"} ${suffix}`;
  }
  const weeks = Math.floor(days / 7);
  if (weeks < 5) {
    return `${weeks} week${weeks === 1 ? "" : "s"} ${suffix}`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months} month${months === 1 ? "" : "s"} ${suffix}`;
  }
  const years = Math.floor(days / 365);
  return `${years} year${years === 1 ? "" : "s"} ${suffix}`;
}

document.addEventListener("alpine:init", () => {
  Alpine.data("userTable", () => ({
    users: [],
    filteredUsers: [],
    selectedUsers: [],
    currentPage: 1,
    itemsPerPage: 10,
    searchQuery: "",
    statusFilter: "",
    roleFilter: "",
    sortField: "name",
    sortDirection: "asc",
    isLoading: false,
    apiError: "",
    avatarUrl: getMetaContent("avatar-placeholder", DEFAULT_AVATAR),
    roleChart: null,
    hasLoadedInitial: false,
    recentActivities: [],
    activitiesLoading: false,
    activityError: "",
    init() {
      this.loadUsers();
      this.loadRecentActivities();
    },
    async apiFetch(url, options = {}) {
      const headers = Object.assign(
        {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        options.headers || {}
      );

      const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers,
      });

      let data = {};
      const contentType = response.headers.get("content-type") || "";
      if (response.redirected && !contentType.includes("application/json")) {
        window.location.href = response.url;
        return {};
      }
      if (contentType.includes("application/json")) {
        try {
          data = await response.json();
        } catch (err) {
          data = {};
        }
      }

      if (!response.ok) {
        if (response.status === 401) {
          window.location.href = "/login";
          return {};
        }
        const message = data.message || `Request failed (${response.status})`;
        throw new Error(message);
      }

      if (!contentType.includes("application/json")) {
        throw new Error("Session expired. Please log in again.");
      }

      return data;
    },
    normalizeUser(user) {
      const roles = normalizeRoles(user.roles);
      const primary = pickPrimaryRole(roles);
      const uiRole = roleToUi(primary);
      const label = roleLabel(uiRole);
      const created = dateOnly(user.created_at);

      return {
        id: user.id,
        name: user.name || "",
        email: user.email || "",
        role: uiRole,
        roleLabel: label,
        roles,
        status: statusToUi(user.status),
        lastActive: created || "N/A",
        joinDate: created || "",
        avatar: this.avatarUrl || DEFAULT_AVATAR,
        phone: "",
        department: label,
      };
    },
    async loadUsers() {
      this.isLoading = true;
      this.apiError = "";
      try {
        const initial = window.__usersData;
        if (!this.hasLoadedInitial && Array.isArray(initial) && initial.length > 0) {
          this.users = initial.map((user) => this.normalizeUser(user));
          this.hasLoadedInitial = true;
        } else {
          const data = await this.apiFetch("/admin/users/data");
          const items = Array.isArray(data.items) ? data.items : [];
          this.users = items.map((user) => this.normalizeUser(user));
        }
        this.selectedUsers = [];
      } catch (err) {
        this.apiError = err.message || "Failed to load users.";
        this.users = [];
        showAlert(this.apiError, "error", "Load Failed");
      } finally {
        this.isLoading = false;
        this.filterUsers();
        this.$nextTick(() => {
          this.initCharts();
        });
      }
    },
    normalizeActivity(activity) {
      const createdAt = activity.created_at || activity.createdAt || null;
      return {
        id: activity.id,
        user: activity.user || "Unknown user",
        action: activity.action || "did activity",
        type: activity.type || "update",
        icon: activity.icon || "activity",
        details: activity.details || "",
        created_at: createdAt,
        time: formatRelativeTime(createdAt),
      };
    },
    async loadRecentActivities() {
      this.activitiesLoading = true;
      this.activityError = "";
      try {
        const data = await this.apiFetch("/admin/users/activity?limit=20");
        const items = Array.isArray(data.items) ? data.items : [];
        this.recentActivities = items.map((item) => this.normalizeActivity(item));
      } catch (err) {
        this.activityError = err.message || "Failed to load recent activity.";
        this.recentActivities = [];
      } finally {
        this.activitiesLoading = false;
      }
    },
    async refreshRecentActivities() {
      await this.loadRecentActivities();
    },
    filterUsers() {
      const query = this.searchQuery.trim().toLowerCase();
      this.filteredUsers = this.users.filter((user) => {
        const name = (user.name || "").toLowerCase();
        const email = (user.email || "").toLowerCase();
        const dept = (user.department || "").toLowerCase();
        const roleText = (user.roleLabel || "").toLowerCase();
        const matchesQuery =
          query === "" ||
          name.includes(query) ||
          email.includes(query) ||
          dept.includes(query) ||
          roleText.includes(query);
        const matchesStatus =
          this.statusFilter === "" || user.status === this.statusFilter;
        const matchesRole = this.roleFilter === "" || user.role === this.roleFilter;
        return matchesQuery && matchesStatus && matchesRole;
      });
      this.sortUsers();
      this.currentPage = 1;
    },
    sortBy(field) {
      if (this.sortField === field) {
        this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
      } else {
        this.sortField = field;
        this.sortDirection = "asc";
      }
      this.sortUsers();
    },
    sortUsers() {
      this.filteredUsers.sort((left, right) => {
        let a = left[this.sortField];
        let b = right[this.sortField];
        if (a === undefined || a === null) {
          a = "";
        }
        if (b === undefined || b === null) {
          b = "";
        }
        if (typeof a === "string") {
          a = a.toLowerCase();
        }
        if (typeof b === "string") {
          b = b.toLowerCase();
        }
        if (a === b) {
          return 0;
        }
        return this.sortDirection === "asc" ? (a > b ? 1 : -1) : a < b ? 1 : -1;
      });
    },
    get paginatedUsers() {
      const start = (this.currentPage - 1) * this.itemsPerPage;
      const end = start + this.itemsPerPage;
      return this.filteredUsers.slice(start, end);
    },
    get totalPages() {
      return Math.ceil(this.filteredUsers.length / this.itemsPerPage);
    },
    get visiblePages() {
      const pages = [];
      const spread = [];
      for (
        let page = Math.max(2, this.currentPage - 2);
        page <= Math.min(this.totalPages - 1, this.currentPage + 2);
        page += 1
      ) {
        pages.push(page);
      }
      if (this.currentPage - 2 > 2) {
        spread.push(1, "...");
      } else {
        spread.push(1);
      }
      spread.push(...pages);
      if (this.currentPage + 2 < this.totalPages - 1) {
        spread.push("...", this.totalPages);
      } else if (this.totalPages > 1) {
        spread.push(this.totalPages);
      }
      return spread.filter((value, index, list) => list.indexOf(value) === index && value <= this.totalPages);
    },
    goToPage(page) {
      if (page >= 1 && page <= this.totalPages) {
        this.currentPage = page;
      }
    },
    toggleUser(userId, checked) {
      const id = Number(userId);
      if (Number.isNaN(id)) {
        return;
      }
      if (checked) {
        if (!this.selectedUsers.includes(id)) {
          this.selectedUsers = [...this.selectedUsers, id];
        }
        return;
      }
      this.selectedUsers = this.selectedUsers.filter((item) => Number(item) !== id);
    },
    toggleAll(checked) {
      if (checked) {
        this.selectedUsers = this.paginatedUsers
          .map((user) => Number(user.id))
          .filter((value) => !Number.isNaN(value));
      } else {
        this.selectedUsers = [];
      }
    },
    openCreateModal() {
      const formData = Alpine.$data(
        document.querySelector('[x-data="userForm"]')
      );
      if (formData) {
        formData.resetForm();
      }
    },
    async createUser(form) {
      const name = `${form.firstName} ${form.lastName}`.trim();
      const payload = {
        name,
        email: form.email.trim(),
        password: form.password,
        role: roleToApi(form.role),
      };
      const data = await this.apiFetch("/admin/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (data.user && form.status === "inactive") {
        await this.apiFetch(`/admin/users/${data.user.id}`,
          {
            method: "PUT",
            body: JSON.stringify({ status: "DISABLED" }),
          }
        );
      }

      await Promise.all([this.loadUsers(), this.loadRecentActivities()]);
    },
    async updateUser(userId, form) {
      const name = `${form.firstName} ${form.lastName}`.trim();
      const payload = {
        name,
        email: form.email.trim(),
        status: statusToApi(form.status),
        role: roleToApi(form.role),
      };

      await this.apiFetch(`/admin/users/${userId}`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        }
      );

      await Promise.all([this.loadUsers(), this.loadRecentActivities()]);
    },
    editUser(user) {
      const formData = Alpine.$data(
        document.querySelector('[x-data="userForm"]')
      );
      if (!formData) {
        return;
      }
      const nameParts = String(user.name || "").trim().split(" ");
      formData.form.firstName = nameParts.shift() || "";
      formData.form.lastName = nameParts.join(" ");
      formData.form.email = user.email || "";
      formData.form.role = user.role || "user";
      formData.form.status = user.status || "active";
      formData.form.password = "";
      formData.editingUserId = user.id;

      const modalEl = document.getElementById("userModal");
      if (modalEl) {
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
      }
    },
    viewUser(user) {
      console.log("Viewing user:", user);
    },
    async deleteUser(user) {
      const confirmed = await confirmDialog(
        `Are you sure you want to deactivate ${user.name}?`,
        {
          confirmText: "Deactivate",
          confirmColor: "var(--bs-danger)",
        }
      );
      if (!confirmed) {
        return;
      }
      try {
        await this.apiFetch(`/admin/users/${user.id}`,
          {
            method: "PUT",
            body: JSON.stringify({ status: "DISABLED" }),
          }
        );
        await Promise.all([this.loadUsers(), this.loadRecentActivities()]);
      } catch (err) {
        showAlert(err.message || "Failed to update user.", "error", "Update Failed");
      }
    },
    async bulkAction(action) {
      if (this.selectedUsers.length === 0) {
        showAlert("Please select users first", "warning", "No Users Selected");
        return;
      }
      let status = null;
      if (action === "activate") {
        status = "ACTIVE";
      }
      if (action === "deactivate" || action === "delete") {
        status = "DISABLED";
      }
      if (!status) {
        return;
      }
      if (action === "delete") {
        const confirmed = await confirmDialog(
          `Are you sure you want to deactivate ${this.selectedUsers.length} users?`,
          {
            confirmText: "Deactivate",
            confirmColor: "var(--bs-danger)",
          }
        );
        if (!confirmed) {
          return;
        }
      }

      this.isLoading = true;
      try {
        for (const userId of this.selectedUsers) {
          await this.apiFetch(`/admin/users/${userId}`,
            {
              method: "PUT",
              body: JSON.stringify({ status }),
            }
          );
        }
        await Promise.all([this.loadUsers(), this.loadRecentActivities()]);
      } catch (err) {
        showAlert(err.message || "Bulk update failed.", "error", "Bulk Update Failed");
      } finally {
        this.isLoading = false;
        this.selectedUsers = [];
      }
    },
    exportUsers() {
      const csv = this.generateCSV(this.filteredUsers);
      this.downloadCSV(csv, "users-export.csv");
    },
    generateCSV(items) {
      const headers = [
        "ID",
        "Name",
        "Email",
        "Role",
        "Status",
        "Department",
        "Join Date",
        "Last Active",
      ];
      const rows = items.map((user) => [
        user.id,
        user.name,
        user.email,
        user.roleLabel || user.role,
        user.status,
        user.department || "",
        user.joinDate,
        user.lastActive,
      ]);
      return [headers, ...rows].map((row) => row.join(",")).join("\n");
    },
    downloadCSV(content, filename) {
      const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.setAttribute("href", url);
      link.setAttribute("download", filename);
      link.style.visibility = "hidden";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },
    sendBulkInvites() {
      if (this.selectedUsers.length === 0) {
        showAlert("Please select users to send invites to", "warning", "No Users Selected");
        return;
      }
      showAlert(`Sent invites to ${this.selectedUsers.length} users`, "success", "Invites Sent");
      this.selectedUsers = [];
    },
    generateReport() {
      const report = {
        generatedAt: new Date().toISOString(),
        totalUsers: this.users.length,
        stats: this.stats,
        departmentBreakdown: this.departmentStats,
        recentActivity: this.recentActivities,
      };
      const json = JSON.stringify(report, null, 2);
      this.downloadCSV(json, "user-report.json");
    },
    get stats() {
      const total = this.users.length;
      const active = this.users.filter((user) => user.status === "active").length;
      const inactive = this.users.filter((user) => user.status === "inactive").length;
      const now = new Date();
      const newThisMonth = this.users.filter((user) => {
        if (!user.joinDate) {
          return false;
        }
        const joinDate = new Date(user.joinDate);
        return joinDate.getMonth() === now.getMonth() && joinDate.getFullYear() === now.getFullYear();
      }).length;

      return {
        total,
        active,
        inactive,
        pending: 0,
        newThisMonth,
        activePercentage: total > 0 ? (active / total) * 100 : 0,
        inactivePercentage: total > 0 ? (inactive / total) * 100 : 0,
        pendingPercentage: 0,
      };
    },
    get departmentStats() {
      const counts = this.users.reduce((acc, user) => {
        const key = user.department || "General";
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }, {});
      const colors = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#0ea5e9", "#8b5cf6"];
      return Object.entries(counts).map(([name, count], index) => ({
        name,
        count,
        percentage: this.users.length > 0 ? Math.round((count / this.users.length) * 100) : 0,
        color: colors[index % colors.length],
      }));
    },
    get systemAlerts() {
      return [
        {
          id: 1,
          title: "User Registration Alert",
          message: "New user registrations require approval",
          type: "warning",
          time: "5 minutes ago",
        },
        {
          id: 2,
          title: "Backup Complete",
          message: "System backup completed successfully",
          type: "success",
          time: "1 hour ago",
        },
        {
          id: 3,
          title: "Maintenance Notice",
          message: "Database maintenance scheduled for tonight",
          type: "info",
          time: "2 hours ago",
        },
      ];
    },
    initCharts() {
      const activeChartEl = document.querySelector("#activeUserChart");
      if (activeChartEl && !activeChartEl.hasAttribute("data-chart-initialized")) {
        activeChartEl.setAttribute("data-chart-initialized", "true");
        const options = {
          series: [{ name: "Active Users", data: [65, 70, 80, 85, 90, 95, 88] }],
          chart: { type: "line", height: 50, sparkline: { enabled: true } },
          stroke: { curve: "smooth", width: 2 },
          colors: ["#10b981"],
        };
        new ApexCharts(activeChartEl, options).render();
      }

      const growthChartEl = document.querySelector("#userGrowthChart");
      if (growthChartEl && !growthChartEl.hasAttribute("data-chart-initialized")) {
        growthChartEl.setAttribute("data-chart-initialized", "true");
        const options = {
          series: [{ name: "New Users", data: [5, 8, 12, 15, 10, 18, 22] }],
          chart: {
            type: "bar",
            height: 250,
            width: "100%",
            toolbar: { show: false },
            parentHeightOffset: 0,
            offsetX: 0,
            offsetY: 0,
            zoom: { enabled: false },
            selection: { enabled: false },
          },
          responsive: [{ breakpoint: 768, options: { chart: { height: 200 } } }],
          colors: ["#6366f1"],
          plotOptions: { bar: { borderRadius: 4, columnWidth: "50%", barHeight: "70%" } },
          xaxis: {
            categories: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            axisBorder: { show: false },
            axisTicks: { show: false },
            labels: { style: { fontSize: "12px", colors: "#64748b" } },
          },
          yaxis: { show: false },
          grid: { show: false },
          dataLabels: { enabled: false },
          tooltip: { theme: "light" },
        };
        new ApexCharts(growthChartEl, options).render();
      }

      const roleChartEl = document.querySelector("#roleDistributionChart");
      if (roleChartEl) {
        const roleCounts = this.users.reduce((acc, user) => {
          const label = user.roleLabel || user.role;
          acc[label] = (acc[label] || 0) + 1;
          return acc;
        }, {});
        const labels = Object.keys(roleCounts);
        const series = Object.values(roleCounts);
        if (this.roleChart) {
          this.roleChart.updateOptions({ labels, series }, true, true);
        } else {
          const options = {
            series,
            chart: { type: "donut", height: 140 },
            labels,
            colors: ["#6366f1", "#10b981", "#f59e0b", "#ef4444"],
            legend: { show: false },
            plotOptions: { pie: { donut: { size: "70%" } } },
            dataLabels: { enabled: false },
            tooltip: { theme: "light" },
            responsive: [{ breakpoint: 480, options: { chart: { width: 200 } } }],
          };
          this.roleChart = new ApexCharts(roleChartEl, options);
          this.roleChart.render();
        }
      }
    },
  }));

  Alpine.data("searchComponent", () => ({
    query: "",
    results: [],
    isLoading: false,
    async search() {
      if (this.query.length < 2) {
        this.results = [];
        return;
      }
      this.isLoading = true;
      await new Promise((resolve) => setTimeout(resolve, 300));
      this.results = [
        { title: "Dashboard", url: "/", type: "page" },
        { title: "Users", url: "/admin/users", type: "page" },
        { title: "Settings", url: "/admin/settings", type: "page" },
        { title: "Analytics", url: "/admin/reports", type: "page" },
        { title: "Security", url: "/admin/security", type: "page" },
        { title: "Help", url: "/help", type: "page" },
      ].filter((entry) => entry.title.toLowerCase().includes(this.query.toLowerCase()));
      const table = Alpine.$data(document.querySelector('[x-data="userTable"]'));
      if (table) {
        table.searchQuery = this.query;
        table.filterUsers();
      }
      this.isLoading = false;
    },
  }));

  Alpine.data("themeSwitch", () => ({
    currentTheme: "light",
    init() {
      this.currentTheme = localStorage.getItem("theme") || "light";
      this.applyTheme();
    },
    toggle() {
      this.currentTheme = this.currentTheme === "light" ? "dark" : "light";
      this.applyTheme();
      localStorage.setItem("theme", this.currentTheme);
    },
    applyTheme() {
      document.documentElement.setAttribute("data-bs-theme", this.currentTheme);
    },
  }));

  Alpine.data("userForm", () => ({
    form: {
      firstName: "",
      lastName: "",
      email: "",
      role: "user",
      status: "active",
      password: "",
    },
    editingUserId: null,
    init() {
      this.resetForm();
    },
    resetForm() {
      this.form = {
        firstName: "",
        lastName: "",
        email: "",
        role: "user",
        status: "active",
        password: "",
      };
      this.editingUserId = null;
    },
    async saveUser() {
      if (!this.form.firstName || !this.form.email) {
        showAlert("Please fill in all required fields", "warning", "Missing Information");
        return;
      }
      if (!this.form.role || !this.form.status) {
        showAlert("Please select role and status", "warning", "Missing Information");
        return;
      }
      if (!this.editingUserId && !this.form.password) {
        showAlert("Password is required for new users", "warning", "Missing Password");
        return;
      }

      const table = Alpine.$data(document.querySelector('[x-data="userTable"]'));
      if (!table) {
        return;
      }

      try {
        if (this.editingUserId) {
          await table.updateUser(this.editingUserId, this.form);
        } else {
          await table.createUser(this.form);
        }
      } catch (err) {
        showAlert(err.message || "Failed to save user.", "error", "Save Failed");
        return;
      }

      const modalEl = document.querySelector("#userModal");
      if (modalEl) {
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
      }
      this.resetForm();
    },
  }));
});
