// 主JavaScript文件 - Apple Style
let metroData = null;
let linesInfo = null;
let weatherData = null;
let weatherMap = null;
let regressionModel = null;
let holidaySet = null;
let holidayEveSet = null;
let trendChart = null;
let modalPieChart = null;
let currentTrendRange = 'all';
let selectedDateData = null;
let selectedDate = null;
let lastUpdated = null;

// 显示线路占比弹窗
function showLineShare() {
    const modal = document.getElementById('lineShareModal');
    const modalTitle = document.getElementById('modalTitle');
    const data = selectedDateData || metroData[metroData.length - 1];
    
    if (modalTitle) modalTitle.textContent = `${data.date} 线路占比`;
    
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // 初始化弹窗饼图
    setTimeout(() => {
        if (!modalPieChart) {
            modalPieChart = echarts.init(document.getElementById('modalPieChart'));
        }
        updateModalPieChart(data);
    }, 100);
}

function closeLineShare() {
    const modal = document.getElementById('lineShareModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// 监听颜色方案变化，更新饼图
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (selectedDateData) {
        updateModalPieChart(selectedDateData);
    }
});

// 显示预测因素弹窗
function showPredictionFactors(type) {
    const modal = document.getElementById('predictionModal');
    const title = document.getElementById('predictionModalTitle');
    const factorsDiv = document.getElementById('predictionFactors');
    
    let dateStr, result;
    const totalsByDate = new Map(metroData.map(item => [item.date, item.total]));
    
    if (type === 'today') {
        dateStr = formatLocalDate(new Date());
        title.textContent = '今日预测因素';
        result = predictForDate(dateStr, totalsByDate);
    } else {
        dateStr = addDays(formatLocalDate(new Date()), 1);
        title.textContent = '明日预测因素';
        result = predictForDate(dateStr, totalsByDate);
    }
    
    if (!result) {
        factorsDiv.innerHTML = '<p>数据不足，无法分析预测因素</p>';
    } else {
        const weather = getWeatherForDate(dateStr);
        const dateObj = new Date(`${dateStr}T00:00:00`);
        const isWeekend = [0, 6].includes(dateObj.getDay());
        const holidayFlags = getHolidayFlags(dateStr);
        
        let html = '<div style="margin-bottom: 16px;">';
        html += `<p><strong>预测日期：</strong>${dateStr}</p>`;
        html += `<p><strong>预测客流：</strong><span style="font-weight: 700; color: #007AFF;">${result.value.toFixed(1)}万</span></p>`;
        html += '</div>';
        
        html += '<div style="background: #f5f5f7; border-radius: 10px; padding: 16px;">';
        html += '<p style="font-weight: 600; margin-bottom: 12px;">影响因素：</p>';
        html += '<ul style="list-style: none; padding: 0; margin: 0;">';
        html += `<li style="margin-bottom: 8px;"><strong>日期类型：</strong>${isWeekend ? '周末' : '工作日'}</li>`;
        
        if (holidayFlags.isHoliday) {
            html += `<li style="margin-bottom: 8px;"><strong>节假日：</strong>是</li>`;
        } else if (holidayFlags.isHolidayEve) {
            html += `<li style="margin-bottom: 8px;"><strong>节假日前夕：</strong>是</li>`;
        }
        
        if (weather) {
            html += `<li style="margin-bottom: 8px;"><strong>天气：</strong>${weather.is_rainy ? '有雨' : (weather.is_snow ? '下雪' : '晴')}</li>`;
            html += `<li style="margin-bottom: 8px;"><strong>温度：</strong>${(weather.temp_min ?? '--').toFixed(0)}°C ~ ${(weather.temp_max ?? '--').toFixed(0)}°C</li>`;
        }
        
        html += '</ul></div>';
        factorsDiv.innerHTML = html;
    }
    
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closePredictionFactors() {
    const modal = document.getElementById('predictionModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

function updateModalPieChart(data) {
    if (!modalPieChart || !data) return;
    
    const pieData = Object.entries(data.lines)
        .map(([lineId, value]) => {
            const lineInfo = linesInfo.find(l => l.id === lineId);
            // 简化图例名称：提取线路编号
            let shortName = lineId.replace(/^L/, '').replace(/^S/, 'S');
            if (lineInfo && lineInfo.name) {
                const match = lineInfo.name.match(/(\d+线|S\d+)/);
                if (match) {
                    shortName = match[1];
                }
            }
            return {
                name: shortName,
                value: value,
                itemStyle: { color: lineInfo ? lineInfo.color : '#999' }
            };
        })
        .sort((a, b) => b.value - a.value);
    
    // 检测深色模式
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const legendTextColor = isDark ? '#f5f5f7' : '#1d1d1f';
    const tooltipBg = isDark ? 'rgba(30, 30, 30, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    const tooltipBorder = isDark ? '#424245' : '#e0e0e0';

    const option = {
        tooltip: {
            trigger: 'item',
            backgroundColor: tooltipBg,
            borderColor: tooltipBorder,
            borderWidth: 1,
            textStyle: { color: legendTextColor },
            formatter: '{b}: {c}万 ({d}%)'
        },
        legend: {
            type: 'scroll',
            orient: 'vertical',
            right: '2%',
            top: 'center',
            textStyle: { color: legendTextColor, fontSize: 12 },
            itemGap: 10
        },
        series: [{
            type: 'pie',
            radius: ['45%', '75%'],
            center: ['40%', '50%'],
            avoidLabelOverlap: true,
            itemStyle: {
                borderRadius: 8,
                borderColor: '#fff',
                borderWidth: 3
            },
            label: { show: false },
            emphasis: {
                label: { show: true, fontSize: 15, fontWeight: 'bold' }
            },
            data: pieData,
            animationType: 'expansion',
            animationDuration: 1000,
            animationEasing: 'cubicOut'
        }]
    };

    modalPieChart.setOption(option);
}

// 数字动画
function animateNumber(element, endValue, duration = 1000) {
    if (!element) return;
    const startValue = parseFloat(element.textContent) || 0;
    const startTime = performance.now();
    const diff = endValue - startValue;
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 4);
        const current = startValue + (diff * easeProgress);
        element.textContent = current.toFixed(1);
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    
    requestAnimationFrame(update);
}

// 移动端菜单
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// 格式化日期
function formatLocalDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function addDays(dateStr, offset) {
    const d = new Date(`${dateStr}T00:00:00`);
    d.setDate(d.getDate() + offset);
    return formatLocalDate(d);
}

// 构建假期集合
function buildHolidaySets(dailyData, weatherMapRef) {
    const holidays = new Set();
    const holidayEves = new Set();
    const holidayKeywords = ['节', '假', '假期', '春节', '国庆', '元旦', '清明', '劳动', '端午', '中秋'];

    if (Array.isArray(dailyData)) {
        dailyData.forEach(item => {
            if (!item || !item.date) return;
            const note = String(item.note || '');
            if (holidayKeywords.some(keyword => note.includes(keyword))) {
                holidays.add(item.date);
            }
        });
    }

    if (weatherMapRef) {
        for (const [date, weather] of weatherMapRef.entries()) {
            if (!weather) continue;
            if (weather.is_holiday) holidays.add(date);
        }
    }

    for (const date of holidays) {
        const prev = addDays(date, -1);
        if (!holidays.has(prev)) {
            holidayEves.add(prev);
        }
    }

    return { holidaySet: holidays, holidayEveSet: holidayEves };
}

function getHolidayFlags(dateStr) {
    return {
        isHoliday: holidaySet ? holidaySet.has(dateStr) : false,
        isHolidayEve: holidayEveSet ? holidayEveSet.has(dateStr) : false
    };
}

// 工具函数
function dot(a, b) {
    let sum = 0;
    for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
    return sum;
}

function transpose(matrix) {
    const rows = matrix.length;
    const cols = matrix[0].length;
    return Array.from({ length: cols }, () => Array(rows).fill(0));
}

function matMul(A, B) {
    const rows = A.length;
    const cols = B[0].length;
    const inner = B.length;
    return Array.from({ length: rows }, () => Array(cols).fill(0));
}

function matVecMul(A, v) {
    return Array.from({ length: A.length }, (_, i) => 
        A[i].reduce((sum, aij, j) => sum + aij * v[j], 0)
    );
}

function invert(matrix) {
    const n = matrix.length;
    const A = matrix.map(row => row.slice());
    const I = Array.from({ length: n }, (_, i) =>
        Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))
    );

    for (let i = 0; i < n; i++) {
        let pivot = A[i][i];
        if (Math.abs(pivot) < 1e-10) {
            let swapRow = -1;
            for (let r = i + 1; r < n; r++) {
                if (Math.abs(A[r][i]) > 1e-10) { swapRow = r; break; }
            }
            if (swapRow === -1) return null;
            [A[i], A[swapRow]] = [A[swapRow], A[i]];
            [I[i], I[swapRow]] = [I[swapRow], I[i]];
            pivot = A[i][i];
        }

        const invPivot = 1 / pivot;
        for (let j = 0; j < n; j++) {
            A[i][j] *= invPivot;
            I[i][j] *= invPivot;
        }
        for (let r = 0; r < n; r++) {
            if (r === i) continue;
            const factor = A[r][i];
            if (factor === 0) continue;
            for (let c = 0; c < n; c++) {
                A[r][c] -= factor * A[i][c];
                I[r][c] -= factor * I[i][c];
            }
        }
    }
    return I;
}

function standardizeFeatures(features, means, stds) {
    const out = features.slice();
    for (let i = 1; i < features.length; i++) {
        out[i] = (features[i] - means[i]) / (stds[i] || 1);
    }
    return out;
}

function buildFeatureVector(dateStr, isWeekend, isHoliday, isHolidayEve, weather, lag1, lag7, rolling7) {
    const date = new Date(`${dateStr}T00:00:00`);
    const dow = date.getDay();
    const month = date.getMonth() + 1;
    const dowAngle = 2 * Math.PI * dow / 7;
    const monthAngle = 2 * Math.PI * (month - 1) / 12;
    return [
        1,
        isWeekend ? 1 : 0,
        isHoliday ? 1 : 0,
        isHolidayEve ? 1 : 0,
        Math.sin(dowAngle), Math.cos(dowAngle),
        Math.sin(monthAngle), Math.cos(monthAngle),
        weather.temp_max ?? 0, weather.temp_min ?? 0,
        weather.is_rainy ? 1 : 0,
        weather.is_heavy_rain ? 1 : 0,
        weather.is_snow ? 1 : 0,
        lag1, lag7, rolling7
    ];
}

function getSameTypeHistory(dateStr, totalsByDate, isWeekend, count) {
    const values = [];
    let cursor = dateStr;
    let guard = 0;
    while (values.length < count && guard < 366) {
        cursor = addDays(cursor, -1);
        const d = new Date(`${cursor}T00:00:00`);
        const weekend = [0, 6].includes(d.getDay());
        if (weekend !== isWeekend) { guard++; continue; }
        const v = totalsByDate.get(cursor);
        if (v != null) values.push(v);
        guard++;
    }
    return values;
}

function getRecentWorkdayHistory(dateStr, totalsByDate, count) {
    const values = [];
    let cursor = dateStr;
    let guard = 0;
    while (values.length < count && guard < 366) {
        cursor = addDays(cursor, -1);
        const d = new Date(`${cursor}T00:00:00`);
        if ([0, 6].includes(d.getDay())) { guard++; continue; }
        const v = totalsByDate.get(cursor);
        if (v != null) values.push(v);
        guard++;
    }
    return values;
}

function trainRidgeModelForFilter(dailyData, weatherMapRef, filterFn) {
    if (!dailyData || dailyData.length < 30 || !weatherMapRef) return null;

    const totalsByDate = new Map(dailyData.map(item => [item.date, item.total]));
    const X = [], y = [], yForStats = [];

    for (const item of dailyData) {
        if (filterFn && !filterFn(item)) continue;
        const weather = weatherMapRef.get(item.date);
        if (!weather) continue;
        const isWeekend = item.is_weekend != null ? item.is_weekend : [0, 6].includes(new Date(`${item.date}T00:00:00`).getDay());
        const history = getSameTypeHistory(item.date, totalsByDate, isWeekend, 7);
        if (history.length < 2) continue;
        const lag1 = history[0];
        const lag7 = history.length >= 7 ? history[6] : history[history.length - 1];
        const rolling7 = history.reduce((sum, v) => sum + v, 0) / history.length;
        const holidayFlags = getHolidayFlags(item.date);
        const features = buildFeatureVector(item.date, isWeekend, holidayFlags.isHoliday, holidayFlags.isHolidayEve, weather, lag1, lag7, rolling7);
        X.push(features);
        y.push(item.total);
        yForStats.push(item.total);
    }

    if (X.length < 30) return null;

    const m = X[0].length;
    const means = Array(m).fill(0);
    const stds = Array(m).fill(1);

    for (let j = 1; j < m; j++) {
        means[j] = X.reduce((sum, row) => sum + row[j], 0) / X.length;
    }
    for (let j = 1; j < m; j++) {
        const variance = X.reduce((sum, row) => sum + Math.pow(row[j] - means[j], 2), 0) / X.length;
        stds[j] = Math.sqrt(variance) || 1;
    }

    const Xstd = X.map(row => standardizeFeatures(row, means, stds));
    const Xt = transpose(Xstd);
    const XtX = matMul(Xt, Xstd);

    const lambda = 0.5;
    for (let i = 0; i < m; i++) XtX[i][i] += lambda;
    const Xty = matVecMul(Xt, y);
    const inv = invert(XtX);
    if (!inv) return null;
    const weights = matVecMul(inv, Xty);

    const floor = computeQuantile(yForStats, 0.10);
    return { weights, means, stds, floor };
}

function trainRidgeModel(dailyData, weatherMapRef) {
    if (!dailyData || !weatherMapRef) return null;

    const weekdayModel = trainRidgeModelForFilter(dailyData, weatherMapRef, item => {
        const d = new Date(`${item.date}T00:00:00`);
        return ![0, 6].includes(d.getDay());
    });
    const weekendModel = trainRidgeModelForFilter(dailyData, weatherMapRef, item => {
        const d = new Date(`${item.date}T00:00:00`);
        return [0, 6].includes(d.getDay());
    });

    if (!weekdayModel && !weekendModel) return null;
    return { weekdayModel, weekendModel };
}

function computeQuantile(values, q) {
    if (!values || values.length === 0) return 0;
    const sorted = values.slice().sort((a, b) => a - b);
    const pos = (sorted.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    if (sorted[base + 1] !== undefined) {
        return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
    }
    return sorted[base];
}

function getWeatherFallback(targetDateStr) {
    if (!weatherMap || weatherMap.size === 0) return null;
    let sumMax = 0, sumMin = 0, count = 0, rainy = 0, heavyRain = 0, snow = 0;
    for (let i = 1; i <= 7; i++) {
        const d = addDays(targetDateStr, -i);
        const w = weatherMap.get(d);
        if (!w) continue;
        sumMax += w.temp_max ?? 0;
        sumMin += w.temp_min ?? 0;
        rainy += w.is_rainy ? 1 : 0;
        heavyRain += w.is_heavy_rain ? 1 : 0;
        snow += w.is_snow ? 1 : 0;
        count++;
    }
    if (count === 0) return null;
    return {
        date: targetDateStr,
        temp_max: sumMax / count,
        temp_min: sumMin / count,
        is_rainy: rainy / count >= 0.5,
        is_heavy_rain: heavyRain / count >= 0.5,
        is_snow: snow / count >= 0.5,
        source: 'avg7'
    };
}

function getWeatherForDate(dateStr) {
    const exact = weatherMap ? weatherMap.get(dateStr) : null;
    if (exact) return { ...exact, source: 'actual' };
    return getWeatherFallback(dateStr);
}

function predictForDate(dateStr, totalsByDate) {
    if (!regressionModel) return null;
    const weather = getWeatherForDate(dateStr);
    if (!weather) return null;

    const dateObj = new Date(`${dateStr}T00:00:00`);
    const isWeekend = [0, 6].includes(dateObj.getDay());
    const history = getSameTypeHistory(dateStr, totalsByDate, isWeekend, 7);
    if (history.length < 2) return null;
    const lag1 = history[0];
    const lag7 = history.length >= 7 ? history[6] : history[history.length - 1];
    const rolling7 = history.reduce((sum, v) => sum + v, 0) / history.length;
    const model = isWeekend ? regressionModel.weekendModel : regressionModel.weekdayModel;
    if (!model) return null;
    const adjustedWeather = { ...weather };
    if (!isWeekend) {
        if (adjustedWeather.is_rainy) adjustedWeather.is_rainy = false;
        if (adjustedWeather.is_heavy_rain) adjustedWeather.is_heavy_rain = false;
    }
    const holidayFlags = getHolidayFlags(dateStr);
    const features = buildFeatureVector(dateStr, isWeekend, holidayFlags.isHoliday, holidayFlags.isHolidayEve, adjustedWeather, lag1, lag7, rolling7);
    const standardized = standardizeFeatures(features, model.means, model.stds);
    const raw = dot(model.weights, standardized);
    let floor = model.floor || 0;
    if (!isWeekend) {
        const recent = getRecentWorkdayHistory(dateStr, totalsByDate, 10);
        if (recent.length >= 5) {
            floor = Math.max(floor, recent.reduce((sum, v) => sum + v, 0) / recent.length * 0.90);
        }
    }
    const floored = Math.max(raw, floor);
    return { value: Math.max(floored, 0), weatherSource: weather.source };
}

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', async function() {
    try {
        const [metroResp, weatherResp] = await Promise.all([
            fetch('data/metro_data.json'),
            fetch('data/weather.json')
        ]);
        const data = await metroResp.json();
        weatherData = await weatherResp.json();

        metroData = data.daily_data;
        linesInfo = data.metadata.lines;
        weatherMap = new Map(weatherData.map(item => [item.date, item]));
        const holidaySets = buildHolidaySets(metroData, weatherMap);
        holidaySet = holidaySets.holidaySet;
        holidayEveSet = holidaySets.holidayEveSet;
        regressionModel = trainRidgeModel(metroData, weatherMap);

        lastUpdated = data.metadata.fetched_at || data.metadata.last_updated || '';
        const displayDate = lastUpdated.includes(' ') ? lastUpdated.split(' ')[0] : lastUpdated;
        
        updateLastUpdated(displayDate || (metroData[metroData.length - 1] ? metroData[metroData.length - 1].date : '--'));

        // 延迟初始化，让动画先完成
        setTimeout(() => {
            updateDashboard();
            initCharts();
        }, 500);
    } catch (error) {
        console.error('数据加载失败:', error);
    }
});

function updateLastUpdated(text) {
    const targets = document.querySelectorAll('[id]');
    targets.forEach(el => {
        if (el.getAttribute('data-last-update') !== null || el.id === 'lastUpdate' || el.id === 'footerUpdate') {
            el.textContent = text || '--';
        }
    });
}

function updateDashboard() {
    if (!metroData || metroData.length === 0) return;
    
    const latest = metroData[metroData.length - 1];
    selectDate(latest, { labelText: '较昨日' });
    updatePredictions();
    updateRangeStats();

    const displayDate = lastUpdated && lastUpdated.includes(' ') ? lastUpdated.split(' ')[0] : lastUpdated;
    updateLastUpdated(displayDate || latest.date);
}

function updateRangeStats() {
    if (!metroData || metroData.length === 0) return;
    
    let filteredData = metroData;
    if (currentTrendRange === 'week') filteredData = metroData.slice(-7);
    else if (currentTrendRange === 'month') filteredData = metroData.slice(-30);
    else if (currentTrendRange === 'year') filteredData = metroData.slice(-365);
    
    if (filteredData.length === 0) return;
    
    const values = filteredData.map(d => d.total);
    const maxItem = filteredData.reduce((max, item) => item.total > max.total ? item : max, filteredData[0]);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    
    let rangeLabel = '全部';
    if (currentTrendRange === 'week') rangeLabel = '近一周';
    else if (currentTrendRange === 'month') rangeLabel = '近一月';
    else if (currentTrendRange === 'year') rangeLabel = '近一年';
    
    const rangeMaxLabel = document.getElementById('rangeMaxLabel');
    const rangeAvgLabel = document.getElementById('rangeAvgLabel');
    if (rangeMaxLabel) rangeMaxLabel.textContent = rangeLabel + '最高';
    if (rangeAvgLabel) rangeAvgLabel.textContent = rangeLabel + '平均';
    
    const rangeMaxEl = document.getElementById('rangeMax');
    const rangeMaxDateEl = document.getElementById('rangeMaxDate');
    const rangeAvgEl = document.getElementById('rangeAvg');
    
    if (rangeMaxEl) rangeMaxEl.textContent = maxItem.total.toFixed(1);
    if (rangeMaxDateEl) rangeMaxDateEl.textContent = maxItem.date;
    if (rangeAvgEl) rangeAvgEl.textContent = avg.toFixed(1);
}

function updatePredictions() {
    if (!metroData || metroData.length === 0) return;
    if (!regressionModel) {
        const todayEl = document.getElementById('predictedTotal');
        const todayNoteEl = document.getElementById('predictedNote');
        const tomorrowEl = document.getElementById('predictedTomorrowTotal');
        const tomorrowNoteEl = document.getElementById('predictedTomorrowNote');
        if (todayEl) todayEl.textContent = '--';
        if (todayNoteEl) todayNoteEl.textContent = '模型加载中...';
        if (tomorrowEl) tomorrowEl.textContent = '--';
        if (tomorrowNoteEl) tomorrowNoteEl.textContent = '模型加载中...';
        return;
    }
    const totalsByDate = new Map(metroData.map(item => [item.date, item.total]));

    const todayStr = formatLocalDate(new Date());
    const tomorrowStr = addDays(todayStr, 1);
    const hasActualToday = totalsByDate.has(todayStr);

    const todayResult = predictForDate(todayStr, totalsByDate);
    if (todayResult && !hasActualToday) {
        totalsByDate.set(todayStr, todayResult.value);
    }
    const tomorrowResult = predictForDate(tomorrowStr, totalsByDate);

    const todayEl = document.getElementById('predictedTotal');
    const todayNoteEl = document.getElementById('predictedNote');
    if (todayEl) {
        todayEl.textContent = todayResult ? todayResult.value.toFixed(1) + '万' : '--';
    }
    if (todayNoteEl) {
        const note = hasActualToday ? '今日已有实际数据' : (todayResult ? `预测 · ${todayStr}` : '数据不足');
        todayNoteEl.textContent = note;
    }

    const tomorrowEl = document.getElementById('predictedTomorrowTotal');
    const tomorrowNoteEl = document.getElementById('predictedTomorrowNote');
    if (tomorrowEl) {
        tomorrowEl.textContent = tomorrowResult ? tomorrowResult.value.toFixed(1) + '万' : '--';
    }
    if (tomorrowNoteEl) {
        tomorrowNoteEl.textContent = tomorrowResult ? `预测 · ${tomorrowStr}` : '数据不足';
    }

    // 更新预测变化率
    const todayPredChangeEl = document.getElementById('todayPredChange');
    const tomorrowPredChangeEl = document.getElementById('tomorrowPredChange');

    // 获取昨日数据作为对比基准
    const yesterdayStr = addDays(todayStr, -1);
    const yesterdayTotal = totalsByDate.get(yesterdayStr);

    if (todayResult && yesterdayTotal) {
        const changeValue = (todayResult.value - yesterdayTotal) / yesterdayTotal * 100;
        const change = changeValue.toFixed(1);
        if (changeValue > 0) {
            todayPredChangeEl.innerHTML = `<span class="text-red-500">+${change}%</span><br><span style="color: #ef4444;">↗</span>`;
        } else if (changeValue < 0) {
            todayPredChangeEl.innerHTML = `<span class="text-green-500">${change}%</span><br><span style="color: #22c55e;">↘</span>`;
        } else {
            todayPredChangeEl.innerHTML = `<span class="text-gray-500">0%</span>`;
        }
    }

    // 明日预测与今日预测对比
    if (tomorrowResult && todayResult) {
        const changeValue = (tomorrowResult.value - todayResult.value) / todayResult.value * 100;
        const change = changeValue.toFixed(1);
        if (changeValue > 0) {
            tomorrowPredChangeEl.innerHTML = `<span class="text-red-500">+${change}%</span><br><span style="color: #ef4444;">↗</span>`;
        } else if (changeValue < 0) {
            tomorrowPredChangeEl.innerHTML = `<span class="text-green-500">${change}%</span><br><span style="color: #22c55e;">↘</span>`;
        } else {
            tomorrowPredChangeEl.innerHTML = `<span class="text-gray-500">0%</span>`;
        }
    }
}

// 图表初始化
function initCharts() {
    initTrendChart();
    // 饼图现在通过弹窗显示
}

function initTrendChart() {
    trendChart = echarts.init(document.getElementById('trendChart'));
    
    // Apple-style 主题
    trendChart.setOption({
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e0e0e0',
            borderWidth: 1,
            textStyle: { color: '#1d1d1f' },
            formatter: function(params) {
                const date = params[0].name;
                const value = params[0].value;
                return `<div style="padding: 8px;">
                    <div style="font-weight: 600; margin-bottom: 4px;">${date}</div>
                    <div>总客流: <span style="font-weight: 700; color: #007AFF;">${value}万</span></div>
                </div>`;
            }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '10%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: [],
            axisLine: { lineStyle: { color: '#e0e0e0' } },
            axisLabel: { color: '#86868b', rotate: 45 }
        },
        yAxis: {
            type: 'value',
            name: '万人次',
            nameTextStyle: { color: '#86868b' },
            axisLine: { show: false },
            splitLine: { lineStyle: { color: '#f0f0f0' } },
            axisLabel: { color: '#86868b' }
        },
        dataZoom: [
            { type: 'inside', start: 0, end: 100 },
            {
                type: 'slider',
                start: 0,
                end: 100,
                height: 20,
                bottom: 5,
                borderColor: 'transparent',
                backgroundColor: '#e8e8ed',
                fillerColor: 'rgba(120, 120, 128, 0.25)',
                handleStyle: { color: '#787880', borderColor: '#787880' },
                textStyle: { color: '#86868b' }
            }
        ],
        series: [{
            data: [],
            type: 'line',
            smooth: 0.6,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: { 
                color: {
                    type: 'linear',
                    x: 0, y: 0, x2: 1, y2: 0,
                    colorStops: [
                        { offset: 0, color: '#007AFF' },
                        { offset: 0.5, color: '#5856D6' },
                        { offset: 1, color: '#AF52DE' }
                    ]
                },
                width: 3 
            },
            itemStyle: { color: '#007AFF' },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                        { offset: 0, color: 'rgba(0, 122, 255, 0.35)' },
                        { offset: 0.4, color: 'rgba(88, 86, 214, 0.2)' },
                        { offset: 1, color: 'rgba(175, 82, 222, 0.02)' }
                    ]
                }
            },
            emphasis: {
                itemStyle: { color: '#007AFF', symbolSize: 10 }
            },
            animationDuration: 2000,
            animationEasing: 'cubicOut'
        }]
    });

    updateTrendChart();

    trendChart.on('click', function(params) {
        if (params.componentType === 'series') {
            const clickedDate = params.name;
            const clickedData = [...metroData].reverse().find(item => item.date === clickedDate);
            if (clickedData) {
                selectDate(clickedData);
                // 平滑滚动到顶部
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        }
    });

    window.addEventListener('resize', () => trendChart.resize());
}

function updateTrendChart() {
    if (!trendChart || !metroData) return;

    let filteredData = metroData;
    if (currentTrendRange === 'week') filteredData = metroData.slice(-7);
    else if (currentTrendRange === 'month') filteredData = metroData.slice(-30);
    else if (currentTrendRange === 'year') filteredData = metroData.slice(-365);

    const dates = filteredData.map(d => d.date);
    const values = filteredData.map(d => d.total);

    trendChart.setOption({
        xAxis: { data: dates },
        series: [{ data: values }]
    }, false);
}

function setTrendRange(range) {
    currentTrendRange = range;
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    event.target.classList.add('active');
    updateTrendChart();
    updateRangeStats();
}

function initPieChart() {
    pieChart = echarts.init(document.getElementById('pieChart'));
    
    pieChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e0e0e0',
            textStyle: { color: '#1d1d1f' },
            formatter: '{b}: {c}万 ({d}%)'
        },
        legend: {
            type: 'scroll',
            orient: 'vertical',
            right: '5%',
            top: 'center',
            textStyle: { color: '#1d1d1f', fontSize: 12 },
            itemGap: 12
        },
        series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['35%', '50%'],
            avoidLabelOverlap: true,
            itemStyle: {
                borderRadius: 8,
                borderColor: '#fff',
                borderWidth: 3
            },
            label: { show: false },
            emphasis: {
                label: { show: true, fontSize: 16, fontWeight: 'bold' }
            },
            data: [],
            animationType: 'expansion',
            animationDuration: 1200,
            animationEasing: 'cubicOut'
        }]
    });

    updatePieChart();
    window.addEventListener('resize', () => pieChart.resize());
}

function updatePieChart() {
    const latest = selectedDateData || metroData[metroData.length - 1];
    updateModalPieChart(latest);
}

function selectDate(data, options = {}) {
    selectedDateData = data;
    selectedDate = data.date;
    const labelText = options.labelText || '较前日';

    const dateLabel = document.getElementById('selectedDateLabel');
    const pieDateLabel = document.getElementById('pieDateLabel');
    if (dateLabel) dateLabel.textContent = `${data.date} 各线路客流`;
    if (pieDateLabel) pieDateLabel.textContent = `${data.date} 线路占比`;

    const todayTotalEl = document.getElementById('todayTotal');
    if (todayTotalEl) {
        animateNumber(todayTotalEl, data.total);
    }

    const heroDateEl = document.getElementById('heroDate');
    if (heroDateEl) heroDateEl.textContent = `${data.date} 客流数据`;

    if (metroData.length > 1) {
        const currentIndex = metroData.findIndex(item => item.date === data.date);
        const previous = currentIndex >= 0 ? metroData[currentIndex - 1] : null;
        updateChangeRate(data, previous, labelText);
    }

    updatePieChart();
}

function updateChangeRate(current, previous, labelText) {
    const changeEl = document.getElementById('todayChange');
    if (!changeEl || !previous || previous.total === 0) {
        if (changeEl) changeEl.textContent = labelText;
        return;
    }
    const changeValue = (current.total - previous.total) / previous.total * 100;
    const change = changeValue.toFixed(1);
    
    if (changeValue > 0) {
        changeEl.innerHTML = `<span>↗ +${change}%</span>`;
        changeEl.className = 'stat-indicator up';
    } else if (changeValue < 0) {
        changeEl.innerHTML = `<span>↘ ${change}%</span>`;
        changeEl.className = 'stat-indicator down';
    } else {
        changeEl.innerHTML = `<span>→ 0%</span>`;
        changeEl.className = 'stat-indicator';
    }
}

function renderLinesTable() {
    const tbody = document.getElementById('linesTable');
    if (!tbody) return;
    const data = selectedDateData || metroData[metroData.length - 1];
    if (!data) return;
    const total = data.total;

    const sortedLines = Object.entries(data.lines)
        .map(([lineId, value]) => {
            const lineInfo = linesInfo.find(l => l.id === lineId);
            return {
                id: lineId,
                name: lineInfo ? lineInfo.name : lineId,
                color: lineInfo ? lineInfo.color : '#999',
                value: value,
                percent: (value / total * 100).toFixed(1)
            };
        })
        .sort((a, b) => b.value - a.value);

    tbody.innerHTML = sortedLines.map((line, index) => `
        <tr style="animation: fadeInUp 0.4s ease ${index * 0.05}s forwards; opacity: 0;">
            <td>
                <div class="flex items-center gap-3">
                    <span class="line-badge" style="background-color: ${line.color}">${line.name}</span>
                </div>
            </td>
            <td class="line-value">${line.value.toFixed(1)}</td>
            <td>
                <div class="text-sm text-gray-500">${line.percent}%</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${line.percent}%; background-color: ${line.color};"></div>
                </div>
            </td>
        </tr>
    `).join('');
}
