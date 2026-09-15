const STORAGE_KEY = "trading-business-manager-v1";

const defaultData = {
  settings: {
    startingBalance: 150,
    profitTarget: 64,
    withdrawalTarget: 32,
    currentCycle: 1,
    currentBalance: 150
  },
  trades: [],
  cycles: [],
  daily: []
};

let state = loadState();

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  bindForms();
  setDefaultDates();
  render();
});

function loadState() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return structuredClone(defaultData);
  try {
    return { ...structuredClone(defaultData), ...JSON.parse(saved) };
  } catch {
    return structuredClone(defaultData);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function bindNavigation() {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  document.querySelectorAll("[data-open-tab]").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.openTab));
  });
}

function showTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll(".page-section").forEach((section) => {
    section.classList.toggle("active", section.id === tabId);
  });
  if (tabId === "analytics") drawGrowthChart();
}

function bindForms() {
  document.getElementById("tradeForm").addEventListener("submit", saveTrade);
  document.getElementById("resetTradeForm").addEventListener("click", resetTradeForm);
  document.getElementById("tradeSearch").addEventListener("input", renderTrades);
  document.getElementById("cycleSettingsForm").addEventListener("submit", saveCycleSettings);
  document.getElementById("completeCycleForm").addEventListener("submit", completeCycle);
  document.getElementById("dailyForm").addEventListener("submit", saveDaily);
  document.getElementById("resetDailyForm").addEventListener("click", resetDailyForm);
  document.getElementById("exportData").addEventListener("click", exportData);
  document.getElementById("importData").addEventListener("change", importData);
  document.getElementById("resetData").addEventListener("click", resetData);
}

function setDefaultDates() {
  document.getElementById("tradeDate").value = new Date().toISOString().slice(0, 16);
  document.getElementById("dailyDate").value = new Date().toISOString().slice(0, 10);
}

async function saveTrade(event) {
  event.preventDefault();
  const id = document.getElementById("tradeId").value || crypto.randomUUID();
  const existing = state.trades.find((trade) => trade.id === id);
  const pnl = numberValue("tradePnl");
  const beforeImage = await readImage("tradeBefore");
  const afterImage = await readImage("tradeAfter");
  const trade = {
    id,
    date: value("tradeDate"),
    session: value("tradeSession"),
    pair: value("tradePair").toUpperCase(),
    direction: value("tradeDirection"),
    lotSize: numberValue("tradeLot"),
    entry: numberValue("tradeEntry"),
    exit: numberValue("tradeExit"),
    stopLoss: numberValue("tradeSl"),
    takeProfit: numberValue("tradeTp"),
    riskPercent: numberValue("tradeRisk"),
    result: value("tradeResult"),
    pnl,
    pnlPercent: numberValue("tradePnlPercent"),
    holdingTime: value("tradeHolding"),
    checklist: checkedRules(),
    notes: value("tradeNotes"),
    beforeImage: beforeImage || existing?.beforeImage || "",
    afterImage: afterImage || existing?.afterImage || ""
  };

  if (existing) {
    state.trades = state.trades.map((item) => (item.id === id ? trade : item));
    state.settings.currentBalance += pnl - existing.pnl;
  } else {
    state.trades.push(trade);
    state.settings.currentBalance += pnl;
  }
  saveState();
  resetTradeForm();
  render();
}

function readImage(inputId) {
  const file = document.getElementById(inputId).files[0];
  if (!file) return Promise.resolve("");
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

function checkedRules() {
  return [...document.querySelectorAll(".checklist input:checked")].map((input) => input.value);
}

function saveCycleSettings(event) {
  event.preventDefault();
  const oldBalance = state.settings.currentBalance;
  state.settings.startingBalance = numberValue("startingBalance");
  state.settings.profitTarget = numberValue("profitTarget");
  state.settings.withdrawalTarget = numberValue("withdrawalTarget");
  if (!state.trades.length && !state.cycles.length) state.settings.currentBalance = state.settings.startingBalance;
  if (oldBalance === 0) state.settings.currentBalance = state.settings.startingBalance;
  saveState();
  render();
}

function completeCycle(event) {
  event.preventDefault();
  const profit = currentCycleProfit();
  if (profit < state.settings.profitTarget) {
    alert("The current cycle has not reached the profit target yet.");
    return;
  }
  const balanceBeforeWithdrawal = state.settings.currentBalance;
  const withdrawal = state.settings.withdrawalTarget;
  const remainingBalance = balanceBeforeWithdrawal - withdrawal;
  state.cycles.push({
    id: crypto.randomUUID(),
    cycleNumber: state.settings.currentCycle,
    completedAt: new Date().toISOString(),
    startingBalance: currentCycleStartBalance(),
    profitTarget: state.settings.profitTarget,
    profitAchieved: profit,
    balanceBeforeWithdrawal,
    withdrawal,
    remainingBalance,
    remarks: value("cycleRemarks")
  });
  state.settings.currentBalance = remainingBalance;
  state.settings.currentCycle += 1;
  document.getElementById("cycleRemarks").value = "";
  saveState();
  render();
}

function saveDaily(event) {
  event.preventDefault();
  const id = document.getElementById("dailyId").value || crypto.randomUUID();
  const entry = {
    id,
    date: value("dailyDate"),
    pnl: numberValue("dailyPnl"),
    emotions: value("dailyEmotions"),
    rules: value("dailyRules"),
    lessons: value("dailyLessons")
  };
  const existing = state.daily.some((item) => item.id === id);
  state.daily = existing ? state.daily.map((item) => (item.id === id ? entry : item)) : [...state.daily, entry];
  saveState();
  resetDailyForm();
  render();
}

function render() {
  renderSettings();
  renderDashboard();
  renderTrades();
  renderCycle();
  renderDaily();
  renderAnalytics();
}

function renderSettings() {
  document.getElementById("startingBalance").value = state.settings.startingBalance;
  document.getElementById("profitTarget").value = state.settings.profitTarget;
  document.getElementById("withdrawalTarget").value = state.settings.withdrawalTarget;
}

function renderDashboard() {
  const stats = calculateStats();
  renderMetricGrid("dashboardMetrics", [
    ["Current Account Balance", money.format(state.settings.currentBalance)],
    ["Current Cycle", `Cycle ${state.settings.currentCycle}`],
    ["Current Profit", money.format(currentCycleProfit())],
    ["Profit Remaining", money.format(Math.max(state.settings.profitTarget - currentCycleProfit(), 0))],
    ["Amount Ready to Withdraw", money.format(currentCycleProfit() >= state.settings.profitTarget ? state.settings.withdrawalTarget : 0)],
    ["Total Withdrawn", money.format(totalWithdrawn())],
    ["Total Profit Generated", money.format(totalProfit())],
    ["Win Rate", `${stats.winRate}%`],
    ["Average Win", money.format(stats.averageWin)],
    ["Average Loss", money.format(stats.averageLoss)],
    ["Risk-to-Reward Ratio", stats.riskReward],
    ["Total Trades", state.trades.length],
    ["Winning Streak", stats.currentWinStreak],
    ["Losing Streak", stats.currentLossStreak]
  ]);

  document.getElementById("cycleBadge").textContent = `Cycle ${state.settings.currentCycle}`;
  document.getElementById("cycleProgressText").textContent = `${money.format(currentCycleProfit())} / ${money.format(state.settings.profitTarget)}`;
  document.getElementById("cycleRemainingText").textContent = `${money.format(Math.max(state.settings.profitTarget - currentCycleProfit(), 0))} remaining`;
  const progressPercent = state.settings.profitTarget ? Math.max(0, Math.min((currentCycleProfit() / state.settings.profitTarget) * 100, 100)) : 0;
  document.getElementById("cycleProgressFill").style.width = `${progressPercent}%`;
  const recent = sortedTrades().slice(0, 5);
  document.getElementById("recentTradeCount").textContent = `${recent.length} shown`;
  renderList("recentTrades", recent.map(tradeSummary));
}

function renderMetricGrid(targetId, items) {
  document.getElementById(targetId).innerHTML = items.map(([label, valueText]) => `
    <article class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(valueText))}</strong>
    </article>
  `).join("");
}

function renderTrades() {
  const query = document.getElementById("tradeSearch")?.value.toLowerCase() || "";
  const rows = sortedTrades().filter((trade) => JSON.stringify(trade).toLowerCase().includes(query));
  document.getElementById("tradeTable").innerHTML = rows.length ? rows.map((trade) => `
    <tr>
      <td>${formatDate(trade.date)}</td>
      <td>${escapeHtml(trade.session)}</td>
      <td>${escapeHtml(trade.pair)}</td>
      <td>${escapeHtml(trade.direction)}</td>
      <td>${resultBadge(trade.result)}</td>
      <td class="${trade.pnl >= 0 ? "profit" : "loss"}">${money.format(trade.pnl)}</td>
      <td>${trade.checklist.length}/10</td>
      <td>
        <button class="text-button" onclick="editTrade('${trade.id}')">Edit</button>
        <button class="text-button danger" onclick="deleteTrade('${trade.id}')">Delete</button>
      </td>
    </tr>
  `).join("") : `<tr><td colspan="8"><div class="empty-state">No trades match this view.</div></td></tr>`;
  renderList("tradeCards", rows.map((trade) => `
    <article class="list-item">
      <strong>${formatDate(trade.date)} | ${escapeHtml(trade.pair)} ${escapeHtml(trade.direction)} | ${resultBadge(trade.result)} | <span class="${trade.pnl >= 0 ? "profit" : "loss"}">${money.format(trade.pnl)}</span></strong>
      <span>${escapeHtml(trade.session)} session | Lot ${trade.lotSize} | Entry ${trade.entry} | Exit ${trade.exit} | Risk ${trade.riskPercent}%</span>
      <p><b>Checklist:</b> ${trade.checklist.length ? escapeHtml(trade.checklist.join(", ")) : "No confirmations checked"}</p>
      <p><b>Notes:</b> ${escapeHtml(trade.notes)}</p>
      ${trade.beforeImage || trade.afterImage ? `
        <div class="screenshot-row">
          ${trade.beforeImage ? `<img src="${trade.beforeImage}" alt="Before trade screenshot">` : ""}
          ${trade.afterImage ? `<img src="${trade.afterImage}" alt="After trade screenshot">` : ""}
        </div>
      ` : ""}
    </article>
  `));
}

function renderCycle() {
  const startBalance = currentCycleStartBalance();
  const beforeWithdrawal = state.settings.currentBalance;
  const remaining = beforeWithdrawal - state.settings.withdrawalTarget;
  document.getElementById("cycleCompletionSummary").innerHTML = [
    ["Cycle", `Cycle ${state.settings.currentCycle}`],
    ["Starting Balance", money.format(startBalance)],
    ["Current Profit", money.format(currentCycleProfit())],
    ["Balance Before Withdrawal", money.format(beforeWithdrawal)],
    ["Withdrawal", money.format(state.settings.withdrawalTarget)],
    ["Remaining Balance", money.format(remaining)]
  ].map(([label, valueText]) => `<div class="summary-row"><span>${label}</span><strong>${valueText}</strong></div>`).join("");

  renderList("cycleHistory", [...state.cycles].reverse().map((cycle) => `
    <article class="list-item">
      <strong>Cycle ${cycle.cycleNumber} completed ${formatDate(cycle.completedAt)}</strong>
      <span>${money.format(cycle.startingBalance)} to ${money.format(cycle.balanceBeforeWithdrawal)} | Withdrew ${money.format(cycle.withdrawal)} | New balance ${money.format(cycle.remainingBalance)}</span>
      <p>${escapeHtml(cycle.remarks)}</p>
    </article>
  `));
}

function renderDaily() {
  renderList("dailyHistory", [...state.daily].sort((a, b) => b.date.localeCompare(a.date)).map((entry) => `
    <article class="list-item">
      <strong>${formatDate(entry.date)} ${entry.pnl ? `| ${money.format(entry.pnl)}` : ""}</strong>
      <p><b>Emotions:</b> ${escapeHtml(entry.emotions || "No entry")}</p>
      <p><b>Rules and news:</b> ${escapeHtml(entry.rules || "No entry")}</p>
      <p><b>Lessons:</b> ${escapeHtml(entry.lessons || "No entry")}</p>
      <div class="item-actions">
        <button class="text-button" onclick="editDaily('${entry.id}')">Edit</button>
        <button class="text-button danger" onclick="deleteDaily('${entry.id}')">Delete</button>
      </div>
    </article>
  `));
}

function renderAnalytics() {
  const stats = calculateStats();
  const bySession = topByProfit("session");
  const byWeekday = topWeekday();
  const byPair = mostTradedPair();
  renderMetricGrid("analyticsMetrics", [
    ["Winning Trades", stats.wins],
    ["Losing Trades", stats.losses],
    ["Most Profitable Session", bySession.label],
    ["Most Profitable Weekday", byWeekday.label],
    ["Most Traded Pair", byPair],
    ["Largest Win", money.format(stats.largestWin)],
    ["Largest Loss", money.format(stats.largestLoss)],
    ["Average Holding Time", averageHoldingTime()]
  ]);
  renderList("checklistInsights", checklistInsights());
  renderList("periodStats", periodStats());
  drawGrowthChart();
}

function renderList(targetId, items) {
  document.getElementById(targetId).innerHTML = items.length ? items.join("") : document.getElementById("emptyStateTemplate").innerHTML;
}

function tradeSummary(trade) {
  return `
    <article class="list-item">
      <strong>${escapeHtml(trade.pair)} ${escapeHtml(trade.direction)} | ${resultBadge(trade.result)}</strong>
      <span class="${trade.pnl >= 0 ? "profit" : "loss"}">${money.format(trade.pnl)}</span>
      <p>${escapeHtml(trade.notes)}</p>
    </article>
  `;
}

function calculateStats() {
  const wins = state.trades.filter((trade) => trade.result === "Win");
  const losses = state.trades.filter((trade) => trade.result === "Loss");
  const averageWin = average(wins.map((trade) => trade.pnl));
  const averageLoss = average(losses.map((trade) => trade.pnl));
  const sorted = sortedTrades().reverse();
  let currentWinStreak = 0;
  let currentLossStreak = 0;
  for (const trade of sorted) {
    if (trade.result === "Win" && currentLossStreak === 0) currentWinStreak += 1;
    else if (trade.result === "Loss" && currentWinStreak === 0) currentLossStreak += 1;
    else break;
  }
  return {
    wins: wins.length,
    losses: losses.length,
    winRate: state.trades.length ? Math.round((wins.length / state.trades.length) * 100) : 0,
    averageWin,
    averageLoss,
    riskReward: averageLoss ? `${Math.abs(averageWin / averageLoss).toFixed(2)}R` : "0R",
    largestWin: Math.max(0, ...wins.map((trade) => trade.pnl)),
    largestLoss: Math.min(0, ...losses.map((trade) => trade.pnl)),
    currentWinStreak,
    currentLossStreak
  };
}

function currentCycleStartBalance() {
  const lastCycle = state.cycles[state.cycles.length - 1];
  return lastCycle ? lastCycle.remainingBalance : state.settings.startingBalance;
}

function currentCycleProfit() {
  return state.settings.currentBalance - currentCycleStartBalance();
}

function totalProfit() {
  return state.trades.reduce((sum, trade) => sum + trade.pnl, 0);
}

function totalWithdrawn() {
  return state.cycles.reduce((sum, cycle) => sum + cycle.withdrawal, 0);
}

function sortedTrades() {
  return [...state.trades].sort((a, b) => new Date(b.date) - new Date(a.date));
}

function topByProfit(key) {
  const totals = groupProfit((trade) => trade[key]);
  return maxGroup(totals);
}

function topWeekday() {
  const totals = groupProfit((trade) => new Date(trade.date).toLocaleDateString("en-US", { weekday: "long" }));
  return maxGroup(totals);
}

function mostTradedPair() {
  const counts = {};
  state.trades.forEach((trade) => counts[trade.pair] = (counts[trade.pair] || 0) + 1);
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "None";
}

function groupProfit(labeler) {
  return state.trades.reduce((groups, trade) => {
    const label = labeler(trade) || "Unknown";
    groups[label] = (groups[label] || 0) + trade.pnl;
    return groups;
  }, {});
}

function maxGroup(groups) {
  const top = Object.entries(groups).sort((a, b) => b[1] - a[1])[0];
  return top ? { label: `${top[0]} (${money.format(top[1])})`, value: top[1] } : { label: "None", value: 0 };
}

function checklistInsights() {
  const rules = {};
  state.trades.forEach((trade) => {
    trade.checklist.forEach((rule) => {
      rules[rule] ||= { total: 0, wins: 0, profit: 0 };
      rules[rule].total += 1;
      rules[rule].wins += trade.result === "Win" ? 1 : 0;
      rules[rule].profit += trade.pnl;
    });
  });
  const insights = Object.entries(rules)
    .filter(([, data]) => data.total > 0)
    .sort((a, b) => b[1].profit - a[1].profit)
    .slice(0, 8)
    .map(([rule, data]) => {
      const winRate = Math.round((data.wins / data.total) * 100);
      return `<article class="list-item"><strong>${escapeHtml(rule)}</strong><span>${winRate}% win rate across ${data.total} trades | ${money.format(data.profit)}</span></article>`;
    });
  if (state.trades.some((trade) => trade.checklist.length < 10 && trade.result === "Loss")) {
    insights.unshift(`<article class="list-item"><strong>Skipped Checklist Warning</strong><span>Some losses happened when not all rules were checked. Review those entries before increasing risk.</span></article>`);
  }
  return insights;
}

function periodStats() {
  const monthly = groupProfit((trade) => trade.date.slice(0, 7));
  const weekly = groupProfit((trade) => `${new Date(trade.date).getFullYear()} W${weekNumber(new Date(trade.date))}`);
  return [
    ...Object.entries(monthly).sort().reverse().slice(0, 6).map(([period, profit]) => `<article class="list-item"><strong>Month ${period}</strong><span>${money.format(profit)}</span></article>`),
    ...Object.entries(weekly).sort().reverse().slice(0, 6).map(([period, profit]) => `<article class="list-item"><strong>Week ${period}</strong><span>${money.format(profit)}</span></article>`)
  ];
}

function drawGrowthChart() {
  const canvas = document.getElementById("growthChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = 220 * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0, 0, rect.width, 220);
  const points = [state.settings.startingBalance];
  sortedTrades().reverse().forEach((trade) => points.push(points[points.length - 1] + trade.pnl));
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  ctx.strokeStyle = "#dfe6dc";
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i += 1) {
    const y = 20 + i * 45;
    ctx.beginPath();
    ctx.moveTo(20, y);
    ctx.lineTo(rect.width - 20, y);
    ctx.stroke();
  }
  ctx.strokeStyle = "#1f7a5a";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 24 + (index / Math.max(points.length - 1, 1)) * (rect.width - 48);
    const y = 200 - ((point - min) / range) * 170;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#17201b";
  ctx.font = "12px sans-serif";
  ctx.fillText(`Start ${money.format(points[0])}`, 24, 214);
  ctx.fillText(`Now ${money.format(points[points.length - 1])}`, rect.width - 120, 214);
}

function averageHoldingTime() {
  const minutes = state.trades.map((trade) => parseHoldingMinutes(trade.holdingTime)).filter(Boolean);
  if (!minutes.length) return "Not tracked";
  const avg = Math.round(average(minutes));
  return `${Math.floor(avg / 60)}h ${avg % 60}m`;
}

function parseHoldingMinutes(text) {
  const hours = Number((text || "").match(/(\d+)\s*h/)?.[1] || 0);
  const minutes = Number((text || "").match(/(\d+)\s*m/)?.[1] || 0);
  return hours * 60 + minutes;
}

function editTrade(id) {
  const trade = state.trades.find((item) => item.id === id);
  if (!trade) return;
  document.getElementById("tradeId").value = trade.id;
  setValue("tradeDate", trade.date);
  setValue("tradeSession", trade.session);
  setValue("tradePair", trade.pair);
  setValue("tradeDirection", trade.direction);
  setValue("tradeLot", trade.lotSize);
  setValue("tradeEntry", trade.entry);
  setValue("tradeExit", trade.exit);
  setValue("tradeSl", trade.stopLoss);
  setValue("tradeTp", trade.takeProfit);
  setValue("tradeRisk", trade.riskPercent);
  setValue("tradeResult", trade.result);
  setValue("tradePnl", trade.pnl);
  setValue("tradePnlPercent", trade.pnlPercent);
  setValue("tradeHolding", trade.holdingTime);
  setValue("tradeNotes", trade.notes);
  document.querySelectorAll(".checklist input").forEach((input) => input.checked = trade.checklist.includes(input.value));
  showTab("trades");
}

function deleteTrade(id) {
  const trade = state.trades.find((item) => item.id === id);
  if (!trade || !confirm("Delete this trade?")) return;
  state.trades = state.trades.filter((item) => item.id !== id);
  state.settings.currentBalance -= trade.pnl;
  saveState();
  render();
}

function editDaily(id) {
  const entry = state.daily.find((item) => item.id === id);
  if (!entry) return;
  document.getElementById("dailyId").value = entry.id;
  setValue("dailyDate", entry.date);
  setValue("dailyPnl", entry.pnl);
  setValue("dailyEmotions", entry.emotions);
  setValue("dailyRules", entry.rules);
  setValue("dailyLessons", entry.lessons);
}

function deleteDaily(id) {
  if (!confirm("Delete this daily journal entry?")) return;
  state.daily = state.daily.filter((item) => item.id !== id);
  saveState();
  render();
}

function resetTradeForm() {
  document.getElementById("tradeForm").reset();
  document.getElementById("tradeId").value = "";
  setDefaultDates();
}

function resetDailyForm() {
  document.getElementById("dailyForm").reset();
  document.getElementById("dailyId").value = "";
  setDefaultDates();
}

function exportData() {
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `trading-business-manager-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function importData(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      state = { ...structuredClone(defaultData), ...JSON.parse(reader.result) };
      saveState();
      render();
      alert("Data imported successfully.");
    } catch {
      alert("That file could not be imported.");
    }
  };
  reader.readAsText(file);
}

function resetData() {
  if (!confirm("Reset all local trading app data?")) return;
  state = structuredClone(defaultData);
  saveState();
  render();
}

function value(id) {
  return document.getElementById(id).value.trim();
}

function setValue(id, newValue) {
  document.getElementById(id).value = newValue ?? "";
}

function numberValue(id) {
  return Number(document.getElementById(id).value || 0);
}

function average(values) {
  return values.length ? values.reduce((sum, valueItem) => sum + valueItem, 0) / values.length : 0;
}

function formatDate(date) {
  if (!date) return "No date";
  return shortDate.format(new Date(date));
}

function resultBadge(result) {
  const className = result === "Win" ? "profit" : result === "Loss" ? "loss" : "muted";
  return `<span class="${className}">${escapeHtml(result)}</span>`;
}

function weekNumber(date) {
  const firstDay = new Date(date.getFullYear(), 0, 1);
  const pastDays = Math.floor((date - firstDay) / 86400000);
  return Math.ceil((pastDays + firstDay.getDay() + 1) / 7);
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[char]);
}
