console.info("%c 合燃华润燃气卡片 \n%c        v1.1 ", "color: orange; font-weight: bold; background: black", "color: white; font-weight: bold; background: black");
import { LitElement, html, css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class HFCRGasCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
    };
  }

  static get styles() {
    return css`
      .form {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 16px;
      }
      label {
        font-weight: bold;
        font-size: 14px;
        color: var(--primary-text-color);
      }
      select, input {
        padding: 8px 12px;
        border: 1px solid var(--primary-color);
        border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        font-size: 14px;
      }
    `;
  }

  render() {
    if (!this.hass) return html``;

    const entities = Object.keys(this.hass.states).filter(
      (e) => e.startsWith("sensor.hfcrgas_") && e.includes("daily_gas_usage_30d")
    );

    return html`
      <div class="form">
        <label>实体：
          <select
            @change=${this._valueChanged}
            .value=${this.config.entity || ""}
            name="entity"
          >
            <option value="">-- 选择实体 --</option>
            ${entities.map(
              (e) => html`<option value="${e}" ?selected=${this.config.entity === e}>${e}</option>`
            )}
          </select>
        </label>
        <label>标题：
          <input
            type="text"
            @change=${this._valueChanged}
            .value=${this.config.title || "合燃华润燃气"}
            name="title"
          />
        </label>
        <label>显示天数：
          <input
            type="number"
            @change=${this._valueChanged}
            .value=${this.config.days || 30}
            name="days"
            min="7"
            max="90"
          />
        </label>
      </div>
    `;
  }

  _valueChanged(e) {
    if (!this.config) return;
    const name = e.target.name;
    let value = e.target.value;
    if (name === "days") value = parseInt(value, 10) || 30;
    this.config = { ...this.config, [name]: value };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this.config } }));
  }
}
customElements.define("hfcrgas-card-editor", HFCRGasCardEditor);


class HFCRGasCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _chart: { type: Object },
      _showCalendar: { type: Boolean },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .card {
        background: var(--card-background-color, #fff);
        border-radius: var(--border-radius, 12px);
        box-shadow: var(--box-shadow, 0 2px 8px rgba(0,0,0,0.1));
        overflow: hidden;
        font-family: var(--primary-font-family, sans-serif);
        color: var(--primary-text-color, #333);
      }
      .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 8px;
      }
      .card-title {
        font-size: 18px;
        font-weight: bold;
        color: var(--primary-text-color);
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .card-title img.card-logo {
        width: 28px;
        height: 28px;
        border-radius: 4px;
        object-fit: contain;
      }
      .card-subtitle {
        font-size: 12px;
        color: var(--secondary-text-color, #999);
        margin-top: 2px;
      }
      .summary-row {
        display: flex;
        justify-content: space-around;
        padding: 12px 16px;
        gap: 8px;
      }
      .summary-item {
        text-align: center;
        flex: 1;
      }
      .summary-value {
        font-size: 20px;
        font-weight: bold;
        color: var(--primary-text-color);
      }
      .summary-value.orange { color: #FF6D00; }
      .summary-value.blue { color: #1E88E5; }
      .summary-value.green { color: #43A047; }
      .summary-label {
        font-size: 11px;
        color: var(--secondary-text-color, #999);
        margin-top: 2px;
      }
      .chart-section {
        padding: 4px 12px 12px;
      }
      .chart-title {
        font-size: 13px;
        font-weight: 500;
        color: var(--primary-text-color);
        padding: 0 4px 8px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .chart-title ha-icon {
        --mdi-icon-size: 16px;
        color: #FF6D00;
      }
      #gas-chart-container {
        width: 100%;
        height: 220px;
      }
      .info-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 20px;
        border-top: 1px solid var(--divider-color, #eee);
        font-size: 13px;
      }
      .info-label {
        color: var(--secondary-text-color, #999);
      }
      .info-value {
        color: var(--primary-text-color);
        font-weight: 500;
      }
      .no-data {
        text-align: center;
        padding: 40px 20px;
        color: var(--secondary-text-color, #999);
        font-size: 14px;
      }

      /* 日历按钮 */
      .calendar-toggle {
        display: flex;
        justify-content: center;
        padding: 6px 16px 10px;
      }
      .calendar-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 16px;
        border-radius: 20px;
        border: 1px solid var(--divider-color, #eee);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .calendar-btn:hover {
        background: var(--primary-color, #FF6D00);
        color: #fff;
        border-color: var(--primary-color, #FF6D00);
      }
      .calendar-btn.active {
        background: #FF6D00;
        color: #fff;
        border-color: #FF6D00;
      }

      /* 日历样式 */
      .calendar-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        grid-template-rows: auto auto repeat(6, 1fr) auto;
        gap: 0;
        padding: 8px 12px 12px;
        margin: 0 8px 8px;
        border-radius: 10px;
        background: var(--card-background-color, #fff);
      }
      .cal-nav-row {
        display: flex;
        align-items: center;
        justify-content: center;
        grid-column: 1 / -1;
        gap: 8px;
        padding: 4px 0 8px;
      }
      .cal-nav-btn {
        cursor: pointer;
        user-select: none;
        font-size: 16px;
        padding: 2px 10px;
        border-radius: 6px;
        transition: background 0.15s;
        color: var(--primary-text-color);
      }
      .cal-nav-btn:hover {
        background: rgba(255, 109, 0, 0.15);
      }
      .cal-nav-btn:active {
        transform: scale(0.95);
      }
      .cal-year-month {
        font-size: 15px;
        font-weight: 600;
        min-width: 100px;
        text-align: center;
        color: var(--primary-text-color);
      }
      .cal-today-btn {
        font-size: 12px;
        padding: 2px 8px;
        border-radius: 10px;
        cursor: pointer;
        user-select: none;
        color: #FF6D00;
        border: 1px solid #FF6D00;
        transition: all 0.15s;
      }
      .cal-today-btn:hover {
        background: #FF6D00;
        color: #fff;
      }
      .cal-weekday {
        text-align: center;
        font-size: 12px;
        font-weight: 600;
        padding: 4px 0;
        color: var(--secondary-text-color, #999);
      }
      .cal-day {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 3px 2px;
        min-height: 48px;
        font-size: 11px;
        line-height: 1.3;
        border: 0.5px solid var(--divider-color, rgba(0,0,0,0.06));
        cursor: default;
      }
      .cal-day-num {
        font-weight: 600;
        font-size: 12px;
        color: var(--primary-text-color);
      }
      .cal-day-usage {
        font-size: 10px;
        color: #FF6D00;
        font-weight: 500;
      }
      .cal-day-reading {
        font-size: 9px;
        color: var(--secondary-text-color, #999);
      }
      .cal-day.min-usage {
        background: rgba(76, 175, 80, 0.15);
      }
      .cal-day.max-usage {
        background: rgba(255, 109, 0, 0.15);
      }
      .cal-day.empty {
        border: none;
        min-height: 0;
      }
      .cal-summary-row {
        grid-column: 1 / -1;
        display: flex;
        justify-content: center;
        gap: 24px;
        padding: 8px 0 4px;
        font-size: 13px;
        font-weight: 500;
        border-top: 1px solid var(--divider-color, #eee);
      }
      .cal-summary-item {
        color: var(--primary-text-color);
      }
      .cal-summary-item span {
        color: #FF6D00;
        font-weight: 600;
      }
    `;
  }

  constructor() {
    super();
    this._chart = null;
    this._resizeObserver = null;
    this._lastDaylistHash = null;
    this._showCalendar = false;
    this._calYear = new Date().getFullYear();
    this._calMonth = new Date().getMonth() + 1;
  }

  static getConfigElement() {
    return document.createElement("hfcrgas-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:hfcrgas-card",
      entity: "",
      title: "合燃华润燃气",
      days: 30,
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("请指定实体");
    }
    this.config = { title: "合燃华润燃气", days: 30, ...config };
  }

  getCardSize() {
    return this._showCalendar ? 8 : 5;
  }

  get _entityState() {
    if (!this.hass || !this.config) return null;
    return this.hass.states[this.config.entity];
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._chart) {
      this._chart.destroy();
      this._chart = null;
    }
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  updated(changedProps) {
    super.updated(changedProps);
    if (changedProps.has("hass") || changedProps.has("config")) {
      const entityState = this._entityState;
      const daylist = entityState?.attributes?.daylist;
      const hash = daylist ? JSON.stringify(daylist) : null;
      if (hash !== this._lastDaylistHash || changedProps.has("config")) {
        this._lastDaylistHash = hash;
        this._renderChart();
      }
    }
  }

  firstUpdated() {
    this._resizeObserver = new ResizeObserver(() => {
      if (this._chart) {
        this._chart.destroy();
        this._chart = null;
        this._renderChart();
      }
    });
    const container = this.shadowRoot?.querySelector("#gas-chart-container");
    if (container) {
      this._resizeObserver.observe(container);
    }
  }

  async _loadApexCharts() {
    if (!window.ApexCharts) {
      await new Promise((resolve) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/apexcharts";
        script.onload = resolve;
        document.head.appendChild(script);
      });
    }
  }

  async _renderChart() {
    const entityState = this._entityState;
    if (!entityState || !entityState.attributes || !entityState.attributes.daylist) return;

    const container = this.shadowRoot?.querySelector("#gas-chart-container");
    if (!container) return;

    await this._loadApexCharts();
    if (!window.ApexCharts) return;

    if (this._chart) {
      this._chart.destroy();
      this._chart = null;
    }

    const daylist = entityState.attributes.daylist || [];
    const days = this.config.days || 30;
    const displayData = daylist.slice(-days);

    if (displayData.length === 0) return;

    const categories = displayData.map((d, i) => {
      const parts = d.day.split("-");
      const isFirst = i === 0;
      const isLast = i === displayData.length - 1;
      const isEvery5th = i % 5 === 0;
      return (isFirst || isLast || isEvery5th) ? `${parts[1]}/${parts[2]}` : "";
    });
    const fullDates = displayData.map((d) => d.day);
    const usageData = displayData.map((d) => d.gasUsage || 0);

    const isDark = this.config.theme === "off" ||
      (document.querySelector("home-assistant")?.defaultView?.panel ||
       document.querySelector("home-assistant"))?.__hass?.themes?.darkMode;

    const textColor = isDark ? "#aaa" : "#666";
    const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";

    const options = {
      chart: {
        type: "bar",
        height: 200,
        background: "transparent",
        toolbar: { show: false },
        animations: { enabled: true, speed: 400 },
        fontFamily: "inherit",
      },
      series: [
        {
          name: "用气量(m³)",
          data: usageData,
        },
      ],
      plotOptions: {
        bar: {
          borderRadius: 3,
          columnWidth: "60%",
          colors: {
            ranges: [
              { from: 0.01, to: 0.5, color: "#81C784" },
              { from: 0.5, to: 1.0, color: "#FFB74D" },
              { from: 1.0, to: Infinity, color: "#FF6D00" },
            ],
          },
        },
      },
      dataLabels: { enabled: false },
      xaxis: {
        categories: categories,
        labels: {
          style: { colors: textColor, fontSize: "10px" },
          rotate: 0,
          hideOverlappingLabels: true,
          showDuplicates: false,
        },
        axisBorder: { show: false },
        axisTicks: { show: false },
        crosshairs: { show: false },
      },
      yaxis: {
        labels: {
          style: { colors: textColor, fontSize: "11px" },
          formatter: (val) => val.toFixed(2),
        },
        min: 0,
      },
      grid: {
        borderColor: gridColor,
        strokeDashArray: 3,
        xaxis: { lines: { show: false } },
        yaxis: { lines: { show: true } },
        padding: { left: 4, right: 4, top: 0, bottom: 0 },
      },
      tooltip: {
        theme: isDark ? "dark" : "light",
        custom: ({ series, seriesIndex, dataPointIndex, w }) => {
          const val = series[seriesIndex][dataPointIndex];
          const date = fullDates[dataPointIndex] || "";
          return `<div style="
            padding: 8px 12px;
            background: ${isDark ? "#333" : "#fff"};
            color: ${isDark ? "#eee" : "#333"};
            border-radius: 6px;
            font-size: 13px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
          ">
            <div style="font-weight:500;margin-bottom:4px;">${date}</div>
            <div><span style="color:#FF6D00;font-weight:bold;">${val.toFixed(2)}</span> m³</div>
          </div>`;
        },
      },
      theme: { mode: isDark ? "dark" : "light" },
    };

    this._chart = new window.ApexCharts(container, options);
    this._chart.render();
  }

  /* ===== 日历功能 ===== */

  _getDaylistData() {
    const entityState = this._entityState;
    if (!entityState || !entityState.attributes || !entityState.attributes.daylist) return [];
    return entityState.attributes.daylist;
  }

  _getDaysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }

  _getDayData(year, month, day) {
    const daylist = this._getDaylistData();
    if (!daylist || daylist.length === 0) return null;
    const dateStr = `${year}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
    return daylist.find(item => item.day === dateStr) || null;
  }

  _getMinMaxUsageDays() {
    const daylist = this._getDaylistData();
    if (!daylist || daylist.length === 0) return { minDays: [], maxDays: [] };
    const monthStr = `${this._calYear}-${this._calMonth.toString().padStart(2, "0")}`;
    const monthDays = daylist.filter(item => item.day && item.day.startsWith(monthStr));
    if (monthDays.length === 0) return { minDays: [], maxDays: [] };
    const validDays = monthDays.filter(d => d.gasUsage !== undefined && d.gasUsage !== null);
    if (validDays.length === 0) return { minDays: [], maxDays: [] };
    const minUsage = Math.min(...validDays.map(d => d.gasUsage));
    const maxUsage = Math.max(...validDays.map(d => d.gasUsage));
    const minDays = validDays.filter(d => d.gasUsage === minUsage).map(d => parseInt(d.day.split("-")[2], 10));
    const maxDays = validDays.filter(d => d.gasUsage === maxUsage).map(d => parseInt(d.day.split("-")[2], 10));
    return { minDays, maxDays };
  }

  _getMonthSummary() {
    const daylist = this._getDaylistData();
    if (!daylist || daylist.length === 0) return { totalUsage: 0, days: 0, avgUsage: 0 };
    const monthStr = `${this._calYear}-${this._calMonth.toString().padStart(2, "0")}`;
    const monthDays = daylist.filter(item => item.day && item.day.startsWith(monthStr) && item.gasUsage > 0);
    const totalUsage = monthDays.reduce((sum, d) => sum + (d.gasUsage || 0), 0);
    return {
      totalUsage: totalUsage.toFixed(2),
      days: monthDays.length,
      avgUsage: monthDays.length > 0 ? (totalUsage / monthDays.length).toFixed(2) : "0.00",
    };
  }

  _prevMonth() {
    if (this._calMonth === 1) {
      this._calMonth = 12;
      this._calYear--;
    } else {
      this._calMonth--;
    }
    this.requestUpdate();
  }

  _nextMonth() {
    if (this._calMonth === 12) {
      this._calMonth = 1;
      this._calYear++;
    } else {
      this._calMonth++;
    }
    this.requestUpdate();
  }

  _goToToday() {
    const today = new Date();
    this._calYear = today.getFullYear();
    this._calMonth = today.getMonth() + 1;
    this.requestUpdate();
  }

  _toggleCalendar() {
    this._showCalendar = !this._showCalendar;
    // 打开日历时回到当前月
    if (this._showCalendar) {
      this._goToToday();
    }
  }

  _renderCalendar() {
    const daysInMonth = this._getDaysInMonth(this._calYear, this._calMonth);
    const firstDayOfMonth = new Date(this._calYear, this._calMonth - 1, 1).getDay();
    // 周一为起始: 0=Mon, 6=Sun
    const adjustedFirstDay = firstDayOfMonth === 0 ? 6 : firstDayOfMonth - 1;
    const { minDays, maxDays } = this._getMinMaxUsageDays();
    const summary = this._getMonthSummary();

    const weekdayNames = ["一", "二", "三", "四", "五", "六", "日"];

    // 星期表头
    const weekdaysRow = weekdayNames.map(d =>
      html`<div class="cal-weekday">${d}</div>`
    );

    // 日期格子
    const dayCells = [];

    // 月初空白格
    for (let i = 0; i < adjustedFirstDay; i++) {
      dayCells.push(html`<div class="cal-day empty"></div>`);
    }

    // 每天的数据
    for (let i = 1; i <= daysInMonth; i++) {
      const dayData = this._getDayData(this._calYear, this._calMonth, i);
      const isMin = minDays.includes(i);
      const isMax = maxDays.includes(i);
      const dayClass = isMin ? "min-usage" : isMax ? "max-usage" : "";

      dayCells.push(html`
        <div class="cal-day ${dayClass}">
          <div class="cal-day-num">${i}</div>
          ${dayData ? html`
            <div class="cal-day-usage">${dayData.gasUsage.toFixed(2)}m³</div>
          ` : ""}
        </div>
      `);
    }

    // 月末填充空白格
    const totalCells = adjustedFirstDay + daysInMonth;
    const remainder = totalCells % 7;
    if (remainder > 0) {
      for (let i = 0; i < 7 - remainder; i++) {
        dayCells.push(html`<div class="cal-day empty"></div>`);
      }
    }

    return html`
      <div class="calendar-grid">
        <!-- 导航行 -->
        <div class="cal-nav-row">
          <div class="cal-nav-btn" @click=${() => this._prevMonth()}>◀</div>
          <div class="cal-year-month">${this._calYear}年${this._calMonth}月</div>
          <div class="cal-nav-btn" @click=${() => this._nextMonth()}>▶</div>
          <div class="cal-today-btn" @click=${() => this._goToToday()}>今月</div>
        </div>

        <!-- 星期表头 -->
        ${weekdaysRow}

        <!-- 日期 -->
        ${dayCells}

        <!-- 月汇总 -->
        <div class="cal-summary-row">
          <div class="cal-summary-item">用气 <span>${summary.totalUsage}</span> m³</div>
          <div class="cal-summary-item">日均 <span>${summary.avgUsage}</span> m³</div>
          <div class="cal-summary-item">用气 <span>${summary.days}</span> 天</div>
        </div>
      </div>
    `;
  }

  render() {
    const entityState = this._entityState;
    if (!entityState) {
      return html`
        <ha-card>
          <div class="no-data">未找到实体数据，请先配置集成</div>
        </ha-card>
      `;
    }

    const attrs = entityState.attributes || {};
    const daylist = attrs.daylist || [];
    const days = this.config.days || 30;

    const balance = attrs["余额"] ?? "-";
    const monthlyUsage = attrs["本月用气量"] ?? "-";
    const yesterdayUsage = attrs["昨日用气量"] ?? "-";
    const meterReading = attrs["表读数"] ?? "-";
    const lastBillDate = attrs["最近出账日期"] ?? "-";
    const lastBillUsage = attrs["最近出账用气量"] ?? "-";
    const lastBillAmount = attrs["最近出账金额"] ?? "-";
    const yearlyUsage = attrs["年度出账用气量"] ?? "-";
    return html`
      <ha-card>
        <div class="card-header">
          <div>
            <div class="card-title">
              <img class="card-logo" src="/hfcrgas-local/logo.png" alt="logo">
              ${this.config.title || "合燃华润燃气"}
            </div>
          </div>
        </div>

        <div class="summary-row">
          <div class="summary-item">
            <div class="summary-value orange">${typeof yesterdayUsage === "number" ? yesterdayUsage.toFixed(2) : yesterdayUsage}</div>
            <div class="summary-label">昨日用气(m³)</div>
          </div>
          <div class="summary-item">
            <div class="summary-value blue">${typeof monthlyUsage === "number" ? monthlyUsage.toFixed(2) : monthlyUsage}</div>
            <div class="summary-label">本月用气(m³)</div>
          </div>
          <div class="summary-item">
            <div class="summary-value green">${typeof balance === "number" ? balance.toFixed(2) : balance}</div>
            <div class="summary-label">余额(元)</div>
          </div>
          <div class="summary-item">
            <div class="summary-value" style="color:var(--primary-text-color)">${typeof meterReading === "number" ? meterReading.toFixed(2) : meterReading}</div>
            <div class="summary-label">表读数(m³)</div>
          </div>
        </div>

        <div class="chart-section">
          <div class="chart-title">
            <ha-icon icon="mdi:chart-bar"></ha-icon>
            近${days}天用气量
          </div>
          <div id="gas-chart-container"></div>
        </div>

        <!-- 日历切换按钮 -->
        <div class="calendar-toggle">
          <div class="calendar-btn ${this._showCalendar ? "active" : ""}" @click=${() => this._toggleCalendar()}>
            <ha-icon icon="mdi:calendar-month" style="--mdi-icon-size:18px;"></ha-icon>
            ${this._showCalendar ? "收起日历" : "用气日历"}
          </div>
        </div>

        <!-- 日历面板 -->
        ${this._showCalendar ? this._renderCalendar() : ""}

        <div class="info-row">
          <span class="info-label">最近出账日期</span>
          <span class="info-value">${lastBillDate || "-"}</span>
        </div>
        <div class="info-row">
          <span class="info-label">最近出账用气量</span>
          <span class="info-value">${typeof lastBillUsage === "number" ? lastBillUsage.toFixed(2) + " m³" : lastBillUsage}</span>
        </div>
        <div class="info-row">
          <span class="info-label">年度出账用气量</span>
          <span class="info-value">${typeof yearlyUsage === "number" ? yearlyUsage.toFixed(2) + " m³" : yearlyUsage}</span>
        </div>
        <div class="info-row">
          <span class="info-label">最近出账金额</span>
          <span class="info-value">${typeof lastBillAmount === "number" ? lastBillAmount.toFixed(2) + " 元" : lastBillAmount}</span>
        </div>
      </ha-card>
    `;
  }
}
customElements.define("hfcrgas-card", HFCRGasCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "hfcrgas-card",
  name: "合燃华润燃气卡片",
  description: "显示30天燃气用量图表和用气日历的卡片",
  documentationURL: "https://github.com/Cyborg2017/ha_hfcrgas",
});

// 通知 HA 前端重新渲染，解决刷新后 "Custom element doesn't exist" 问题
if (window.customCards && window.customCards.length > 0) {
  window.dispatchEvent(new CustomEvent("custom-cards-updated", { bubbles: true }));
  // 延迟再次通知，确保 HA 前端已完全加载
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent("custom-cards-updated", { bubbles: true }));
  }, 1000);
}
