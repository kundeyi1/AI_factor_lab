const API_BASE = "/api";

const state = {
  history: [],
  polling: null,
  backtestReady: false,
  backtestedExpression: "",
};

const els = {
  chatMessages: document.getElementById("chat-messages"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  provider: document.getElementById("ai-provider"),
  apiKey: document.getElementById("api-key"),
  factorName: document.getElementById("factor-name"),
  expression: document.getElementById("factor-expression"),
  description: document.getElementById("factor-description"),
  saveFactor: document.getElementById("save-factor"),
  factorList: document.getElementById("factor-list"),
  runBacktest: document.getElementById("run-backtest"),
  statusPill: document.getElementById("status-pill"),
  statusText: document.getElementById("status-text"),
  overlay: document.getElementById("loading-overlay"),
  progressBar: document.getElementById("progress-bar"),
  progressMessage: document.getElementById("progress-message"),
  progressPercent: document.getElementById("progress-percent"),
  metricsTable: document.getElementById("metrics-table"),
};

document.addEventListener("DOMContentLoaded", () => {
  loadFactors();
  wireEvents();
});

function wireEvents() {
  els.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendChat();
  });

  els.chatInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendChat();
    }
  });

  els.saveFactor.addEventListener("click", saveFactor);
  els.runBacktest.addEventListener("click", startBacktest);
  els.expression.addEventListener("input", markBacktestStale);
  els.factorName.addEventListener("input", markBacktestStale);
}

async function sendChat() {
  const message = els.chatInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  els.chatInput.value = "";
  const loading = appendMessage("ai", "正在把想法转换成因子表达式...");

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: state.history,
        provider: els.provider.value,
        api_key: els.apiKey.value.trim() || null,
      }),
    });
    const payload = await response.json();
    loading.remove();

    if (!response.ok || payload.status !== "success") {
      throw new Error(payload.detail || "AI 请求失败");
    }

    const factor = payload.data;
    state.history.push({ role: "user", content: message });
    state.history.push({ role: "model", content: JSON.stringify(factor) });

    applyFactor(factor);
    const shortDescription = summarizeDescription(factor.description);
    appendMessage(
      "ai",
      `我生成了因子：${factor.name}\n\n解释：${shortDescription}\n\n表达式：\n${factor.expression}\n\n表达式已填入右侧，确认后再点击“开始回测”。`
    );
    setStatus("待回测", "AI 已生成表达式，请人工确认后开始回测。", "pending");
  } catch (error) {
    loading.remove();
    appendMessage("ai", `生成失败：${error.message}`);
    setStatus("生成失败", error.message, "error");
  }
}

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const safeText = escapeHtml(text).replace(/\n/g, "<br>");
  const icon = role === "ai" ? "fa-robot" : "fa-user";
  article.innerHTML = `
    <div class="avatar"><i class="fa-solid ${icon}"></i></div>
    <div class="bubble">${safeText}</div>
  `;
  els.chatMessages.appendChild(article);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return article;
}

function applyFactor(factor) {
  els.factorName.value = factor.name || "";
  els.expression.value = factor.expression || "";
  els.description.textContent = factor.description || "暂无解读。";
  markBacktestStale();
}

function summarizeDescription(description) {
  const text = String(description || "暂无解释。").replace(/\s+/g, " ").trim();
  if (text.length <= 120) return text;
  return `${text.slice(0, 120)}...`;
}

async function loadFactors() {
  try {
    const response = await fetch(`${API_BASE}/factors`);
    const payload = await response.json();
    if (payload.status !== "success") return;
    renderFactors(payload.data);
  } catch (error) {
    console.error("Failed to load factors", error);
  }
}

function renderFactors(factors) {
  els.factorList.innerHTML = "";
  if (!factors.length) {
    els.factorList.innerHTML = '<div class="factor-empty">因子库为空。完成一次回测后，点击右侧保存按钮加入这里。</div>';
    return;
  }

  factors.forEach((factor) => {
    const item = document.createElement("div");
    item.className = "factor-item";

    const loadButton = document.createElement("button");
    loadButton.className = "factor-load";
    loadButton.type = "button";
    loadButton.textContent = factor.name;
    loadButton.title = factor.expression;
    loadButton.addEventListener("click", () => {
      applyFactor(factor);
      setStatus("待回测", "已从因子库载入表达式，请回测后再保存修改。", "pending");
    });

    const deleteButton = document.createElement("button");
    deleteButton.className = "factor-delete";
    deleteButton.type = "button";
    deleteButton.title = "删除因子";
    deleteButton.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
    deleteButton.addEventListener("click", () => deleteFactor(factor.name));

    item.appendChild(loadButton);
    item.appendChild(deleteButton);
    els.factorList.appendChild(item);
  });
}

async function saveFactor() {
  if (!state.backtestReady || state.backtestedExpression !== els.expression.value.trim()) {
    setStatus("暂未保存", "请先完成当前表达式的回测，再保存到因子库。", "error");
    return;
  }

  const factor = {
    name: els.factorName.value.trim(),
    expression: els.expression.value.trim(),
    description: els.description.textContent.trim(),
  };
  if (!factor.name || !factor.expression) {
    setStatus("保存失败", "因子名称和表达式不能为空。", "error");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/factors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(factor),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "success") {
      throw new Error(payload.detail || "保存失败");
    }
    await loadFactors();
    setStatus("已保存", "因子已保存到因子库。", "done");
  } catch (error) {
    setStatus("保存失败", error.message, "error");
  }
}

async function deleteFactor(name) {
  try {
    const response = await fetch(`${API_BASE}/factors/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "success") {
      throw new Error(payload.detail || "删除失败");
    }
    await loadFactors();
    setStatus("已删除", `已从因子库删除：${name}`, "done");
  } catch (error) {
    setStatus("删除失败", error.message, "error");
  }
}

async function startBacktest() {
  const expression = els.expression.value.trim();
  if (!expression) {
    setStatus("无法回测", "请先输入或生成因子表达式。", "error");
    return;
  }

  const payload = {
    expression,
    start_date: document.getElementById("start-date").value,
    end_date: document.getElementById("end-date").value,
    pool: document.getElementById("pool").value,
    freq: document.getElementById("freq").value,
    layers: Number(document.getElementById("layers").value),
  };

  showProgress(0, "提交回测任务...");
  markBacktestStale();
  els.runBacktest.disabled = true;
  setStatus("回测中", "正在下载数据并计算因子。", "pending");

  try {
    const response = await fetch(`${API_BASE}/backtest/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || data.status !== "started") {
      throw new Error(data.detail || "无法启动回测");
    }
    pollBacktest(data.job_id);
  } catch (error) {
    hideProgress();
    els.runBacktest.disabled = false;
    setStatus("回测失败", error.message, "error");
  }
}

function pollBacktest(jobId) {
  clearTimeout(state.polling);

  const pollOnce = async () => {
    try {
      const progressResponse = await fetch(`${API_BASE}/backtest/progress/${jobId}`);
      const progress = await progressResponse.json();
      showProgress(progress.percent, progress.message);

      if (progress.status === "success") {
        state.polling = null;
        await loadBacktestResult(jobId);
      } else if (progress.status === "error") {
        state.polling = null;
        const resultResponse = await fetch(`${API_BASE}/backtest/result/${jobId}`);
        const result = await resultResponse.json();
        throw new Error(result.detail || progress.message || "回测失败");
      } else {
        state.polling = setTimeout(pollOnce, 2500);
      }
    } catch (error) {
      clearTimeout(state.polling);
      state.polling = null;
      hideProgress();
      els.runBacktest.disabled = false;
      setStatus("回测失败", error.message, "error");
    }
  };

  state.polling = setTimeout(pollOnce, 500);
}

async function loadBacktestResult(jobId) {
  try {
    const response = await fetch(`${API_BASE}/backtest/result/${jobId}`);
    const payload = await response.json();
    if (payload.status !== "success") {
      throw new Error(payload.detail || "结果尚未生成");
    }
    renderResults(payload.data);
    state.backtestReady = true;
    state.backtestedExpression = els.expression.value.trim();
    hideProgress();
    els.runBacktest.disabled = false;
    setStatus("回测完成", "结果已更新，可继续调整表达式或保存因子。", "done");
  } catch (error) {
    hideProgress();
    els.runBacktest.disabled = false;
    setStatus("回测失败", error.message, "error");
  }
}

function markBacktestStale() {
  state.backtestReady = false;
  state.backtestedExpression = "";
}

function renderResults(data) {
  const metrics = data.metrics || {};
  setMetric("metric-ann-ret", metrics.long_short_annual_return);
  setMetric("metric-sharpe", metrics.long_short_sharpe);
  setMetric("metric-drawdown", metrics.max_drawdown);
  setMetric("metric-ic", metrics.ic_mean);
  setMetric("metric-icir", metrics.ic_ir);

  renderChart(data.dates || [], data.series || {});
  renderTable(data.table || []);
}

function setMetric(id, value) {
  document.getElementById(id).textContent = value || "--";
}

function renderChart(dates, series) {
  const palette = ["#ff4d5e", "#ff9f1c", "#00d084", "#3d8bfd", "#8453ff", "#ffd500", "#4dd4ac", "#f472b6", "#a3e635", "#38bdf8", "#ffffff"];
  const container = document.getElementById("nav-chart");
  const entries = Object.entries(series);
  if (!entries.length) {
    container.innerHTML = '<div class="empty-chart"><i class="fa-solid fa-chart-line"></i><span>暂无曲线数据</span></div>';
    return;
  }

  if (typeof Plotly === "undefined") {
    renderSvgChart(dates, series, palette);
    return;
  }

  container.innerHTML = "";
  const traces = entries.map(([name, values], index) => ({
    x: dates,
    y: values,
    type: "scatter",
    mode: "lines",
    name,
    line: {
      width: name === "多空对冲组合" ? 3 : 2,
      color: palette[index % palette.length],
    },
  }));

  Plotly.newPlot(
    container,
    traces,
    {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "#9fb2cf" },
      margin: { l: 58, r: 26, t: 24, b: 42 },
      legend: { orientation: "h", y: 1.12 },
      xaxis: { gridcolor: "#243248", zerolinecolor: "#34445e" },
      yaxis: { gridcolor: "#243248", zerolinecolor: "#34445e" },
      hovermode: "x unified",
    },
    { responsive: true, displaylogo: false }
  );
}

function renderSvgChart(dates, series, palette) {
  const entries = Object.entries(series);
  const container = document.getElementById("nav-chart");
  if (!entries.length) {
    container.innerHTML = '<div class="empty-chart"><i class="fa-solid fa-chart-line"></i><span>暂无曲线数据</span></div>';
    return;
  }

  const width = 1000;
  const height = 430;
  const pad = { left: 58, right: 22, top: 42, bottom: 44 };
  const values = entries.flatMap(([, nums]) => nums.filter((x) => Number.isFinite(Number(x))).map(Number));
  const minY = Math.min(...values);
  const maxY = Math.max(...values);
  const spanY = maxY - minY || 1;
  const maxLen = Math.max(...entries.map(([, nums]) => nums.length));

  const xFor = (index) => pad.left + (index / Math.max(maxLen - 1, 1)) * (width - pad.left - pad.right);
  const yFor = (value) => height - pad.bottom - ((Number(value) - minY) / spanY) * (height - pad.top - pad.bottom);
  const lines = entries
    .map(([name, nums], seriesIndex) => {
      const points = nums.map((value, index) => `${xFor(index).toFixed(1)},${yFor(value).toFixed(1)}`).join(" ");
      return `<polyline points="${points}" fill="none" stroke="${palette[seriesIndex % palette.length]}" stroke-width="${name === "多空对冲组合" ? 3 : 2}" stroke-linejoin="round" stroke-linecap="round" />`;
    })
    .join("");

  const legend = entries
    .map(([name], index) => {
      const x = pad.left + (index % 6) * 145;
      const y = 20 + Math.floor(index / 6) * 18;
      return `<g><line x1="${x}" y1="${y}" x2="${x + 24}" y2="${y}" stroke="${palette[index % palette.length]}" stroke-width="3"/><text x="${x + 32}" y="${y + 4}">${escapeHtml(name)}</text></g>`;
    })
    .join("");

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = minY + spanY * ratio;
    const y = yFor(value);
    return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="grid"/><text x="${pad.left - 10}" y="${y + 4}" text-anchor="end">${value.toFixed(2)}</text>`;
  }).join("");

  const xLabels = [0, Math.floor((maxLen - 1) / 2), maxLen - 1].map((index) => {
    const label = dates[index] || "";
    const x = xFor(index);
    return `<text x="${x}" y="${height - 12}" text-anchor="middle">${escapeHtml(label)}</text>`;
  }).join("");

  container.innerHTML = `
    <svg class="fallback-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="分层净值曲线">
      <style>
        .fallback-chart { width: 100%; height: 430px; display: block; }
        .fallback-chart text { fill: #9fb2cf; font: 13px Microsoft YaHei, sans-serif; }
        .fallback-chart .grid { stroke: #243248; stroke-width: 1; }
      </style>
      ${legend}
      ${yTicks}
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#34445e"/>
      <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#34445e"/>
      ${lines}
      ${xLabels}
    </svg>
  `;
}

function renderTable(rows) {
  if (!rows.length) {
    els.metricsTable.innerHTML = "<tr><td colspan=\"6\">暂无数据</td></tr>";
    return;
  }
  els.metricsTable.innerHTML = rows
    .map((row) => {
      const annClass = row.annual_return && row.annual_return.startsWith("-") ? "negative" : "positive";
      const ddClass = row.max_drawdown && row.max_drawdown.startsWith("-") ? "negative" : "";
      return `
        <tr>
          <td><strong>${escapeHtml(row.name)}</strong></td>
          <td class="${annClass}">${escapeHtml(row.annual_return)}</td>
          <td>${escapeHtml(row.annual_volatility)}</td>
          <td>${escapeHtml(row.sharpe)}</td>
          <td class="${ddClass}">${escapeHtml(row.max_drawdown)}</td>
          <td>${escapeHtml(row.win_rate)}</td>
        </tr>
      `;
    })
    .join("");
}

function showProgress(percent, message) {
  els.overlay.hidden = false;
  const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
  els.progressBar.style.width = `${safePercent}%`;
  els.progressPercent.textContent = `${safePercent}%`;
  els.progressMessage.textContent = message || "运行中...";
}

function hideProgress() {
  els.overlay.hidden = true;
  els.progressBar.style.width = "0%";
  els.progressPercent.textContent = "0%";
}

function setStatus(label, text, type) {
  els.statusPill.textContent = label;
  els.statusText.textContent = text;
  els.statusPill.classList.toggle("done", type === "done");
  els.statusPill.classList.toggle("error", type === "error");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
