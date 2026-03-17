// 主JavaScript文件
let metroData = null;
let linesInfo = null;
let weatherData = null;
let weatherMap = null;
let regressionModel = null;
let holidaySet = null;
let holidayEveSet = null;
let trendChart = null;
let pieChart = null;
let currentTrendRange = 'all';
let selectedDateData = null;
let selectedDate = null;
let lastUpdated = null;

// 移动端菜单切换
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// 加载数据
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

        const fetchedAt = data.metadata.fetched_at || '';
        lastUpdated = fetchedAt || data.metadata.last_updated || '';
        const displayDate = lastUpdated.includes(' ') ? lastUpdated.split(' ')[0] : lastUpdated;
        updateLastUpdated(displayDate || (metroData[metroData.length - 1] ? metroData[metroData.length - 1].date : '--'));

        updateDashboard();
        initCharts();
        renderLinesTable();
    } catch (error) {
        console.error('加载数据失败:', error);
        document.querySelector('main').innerHTML = `
            <div class="text-center py-20">
                <p class="text-red-500">数据加载失败，请检查数据文件</p>
            </div>
        `;
    }
});

function updateLastUpdated(text) {
    const targets = document.querySelectorAll('[data-last-update]');
    targets.forEach(el => {
        el.textContent = text || '--';
    });
}

function updateChangeRate(current, previous, labelText) {
    const changeEl = document.getElementById('todayChange');
    if (!changeEl) return;
    if (!previous || previous.total === 0) {
        changeEl.textContent = '--';
        return;
    }
    const changeValue = (current.total - previous.total) / previous.total * 100;
    const change = changeValue.toFixed(1);
    if (changeValue > 0) {
        changeEl.innerHTML = `<span class="text-red-500">↗ +${change}%</span> ${labelText}`;
    } else if (changeValue < 0) {
        changeEl.innerHTML = `<span class="text-green-500">↘ ${change}%</span> ${labelText}`;
    } else {
        changeEl.innerHTML = `<span class="text-gray-500">→ ${change}%</span> ${labelText}`;
    }
}

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

function getSameTypeHistory(dateStr, totalsByDate, isWeekend, count) {
    const values = [];
    let cursor = dateStr;
    let guard = 0;
    while (values.length < count && guard < 366) {
        cursor = addDays(cursor, -1);
        const d = new Date(`${cursor}T00:00:00`);
        const weekend = [0, 6].includes(d.getDay());
        if (weekend !== isWeekend) {
            guard++;
            continue;
        }
        const v = totalsByDate.get(cursor);
        if (v != null) {
            values.push(v);
        }
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
        const weekend = [0, 6].includes(d.getDay());
        if (weekend) {
            guard++;
            continue;
        }
        const v = totalsByDate.get(cursor);
        if (v != null) {
            values.push(v);
        }
        guard++;
    }
    return values;
}

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
    if (holidaySet && holidaySet.has(dateStr)) {
        return { isHoliday: true, isHolidayEve: false };
    }
    return {
        isHoliday: holidaySet ? holidaySet.has(dateStr) : false,
        isHolidayEve: holidayEveSet ? holidayEveSet.has(dateStr) : false
    };
}

function dot(a, b) {
    let sum = 0;
    for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
    return sum;
}

function transpose(matrix) {
    const rows = matrix.length;
    const cols = matrix[0].length;
    const result = Array.from({ length: cols }, () => Array(rows).fill(0));
    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            result[j][i] = matrix[i][j];
        }
    }
    return result;
}

function matMul(A, B) {
    const rows = A.length;
    const cols = B[0].length;
    const inner = B.length;
    const result = Array.from({ length: rows }, () => Array(cols).fill(0));
    for (let i = 0; i < rows; i++) {
        for (let k = 0; k < inner; k++) {
            const aik = A[i][k];
            if (aik === 0) continue;
            for (let j = 0; j < cols; j++) {
                result[i][j] += aik * B[k][j];
            }
        }
    }
    return result;
}

function matVecMul(A, v) {
    const rows = A.length;
    const cols = A[0].length;
    const result = Array(rows).fill(0);
    for (let i = 0; i < rows; i++) {
        let sum = 0;
        for (let j = 0; j < cols; j++) sum += A[i][j] * v[j];
        result[i] = sum;
    }
    return result;
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
                if (Math.abs(A[r][i]) > 1e-10) {
                    swapRow = r;
                    break;
                }
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
        const std = stds[i] || 1;
        out[i] = (features[i] - means[i]) / std;
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
        Math.sin(dowAngle),
        Math.cos(dowAngle),
        Math.sin(monthAngle),
        Math.cos(monthAngle),
        weather.temp_max ?? 0,
        weather.temp_min ?? 0,
        weather.is_rainy ? 1 : 0,
        weather.is_heavy_rain ? 1 : 0,
        weather.is_snow ? 1 : 0,
        lag1,
        lag7,
        rolling7
    ];
}

function trainRidgeModelForFilter(dailyData, weatherMapRef, filterFn) {
    if (!dailyData || dailyData.length < 30 || !weatherMapRef) return null;

    const totalsByDate = new Map(dailyData.map(item => [item.date, item.total]));
    const X = [];
    const y = [];
    const yForStats = [];

    for (const item of dailyData) {
        if (filterFn && !filterFn(item)) continue;
        const weather = weatherMapRef.get(item.date);
        if (!weather) continue;
        const isWeekend = item.is_weekend != null ? item.is_weekend : ([0, 6].includes(new Date(`${item.date}T00:00:00`).getDay()));
        const history = getSameTypeHistory(item.date, totalsByDate, isWeekend, 7);
        if (history.length < 2) continue;
        const lag1 = history[0];
        const lag7 = history.length >= 7 ? history[6] : history[history.length - 1];
        const rolling7 = history.reduce((sum, v) => sum + v, 0) / history.length;
        const holidayFlags = getHolidayFlags(item.date);
        const features = buildFeatureVector(
            item.date,
            isWeekend,
            holidayFlags.isHoliday,
            holidayFlags.isHolidayEve,
            weather,
            lag1,
            lag7,
            rolling7
        );
        X.push(features);
        y.push(item.total);
        yForStats.push(item.total);
    }

    if (X.length < 30) return null;

    const m = X[0].length;
    const means = Array(m).fill(0);
    const stds = Array(m).fill(1);

    for (let j = 1; j < m; j++) {
        let sum = 0;
        for (let i = 0; i < X.length; i++) sum += X[i][j];
        means[j] = sum / X.length;
    }

    for (let j = 1; j < m; j++) {
        let variance = 0;
        for (let i = 0; i < X.length; i++) {
            const diff = X[i][j] - means[j];
            variance += diff * diff;
        }
        stds[j] = Math.sqrt(variance / X.length) || 1;
    }

    const Xstd = X.map(row => standardizeFeatures(row, means, stds));
    const Xt = transpose(Xstd);
    const XtX = matMul(Xt, Xstd);

    const lambda = 0.5;
    for (let i = 0; i < m; i++) {
        XtX[i][i] += lambda;
    }
    const Xty = matVecMul(Xt, y);
    const inv = invert(XtX);
    if (!inv) return null;
    const weights = matVecMul(inv, Xty);

    const floor = computeQuantile(yForStats, 0.10);
    return { weights, means, stds, floor };
}

function trainRidgeModel(dailyData, weatherMapRef) {
    if (!dailyData || !weatherMapRef) return null;

    const weekdayModel = trainRidgeModelForFilter(
        dailyData,
        weatherMapRef,
        item => {
            const d = new Date(`${item.date}T00:00:00`);
            return ![0, 6].includes(d.getDay());
        }
    );
    const weekendModel = trainRidgeModelForFilter(
        dailyData,
        weatherMapRef,
        item => {
            const d = new Date(`${item.date}T00:00:00`);
            return [0, 6].includes(d.getDay());
        }
    );

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
    let sumMax = 0;
    let sumMin = 0;
    let count = 0;
    let rainy = 0;
    let heavyRain = 0;
    let snow = 0;
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
    const fallback = getWeatherFallback(dateStr);
    if (fallback) return fallback;
    return null;
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
    const features = buildFeatureVector(
        dateStr,
        isWeekend,
        holidayFlags.isHoliday,
        holidayFlags.isHolidayEve,
        adjustedWeather,
        lag1,
        lag7,
        rolling7
    );
    const standardized = standardizeFeatures(features, model.means, model.stds);
    const raw = dot(model.weights, standardized);
    if (['2026-03-17', '2026-03-18'].includes(dateStr)) {
        console.log('[debug]', dateStr, {
            isWeekend,
            isHoliday: holidayFlags.isHoliday,
            isHolidayEve: holidayFlags.isHolidayEve,
            weather: adjustedWeather,
            lag1,
            lag7,
            rolling7,
            raw,
            floor: model.floor
        });
    }
    let floor = model.floor || 0;
    if (!isWeekend) {
        const recent = getRecentWorkdayHistory(dateStr, totalsByDate, 10);
        if (recent.length >= 5) {
            const recentAvg = recent.reduce((sum, v) => sum + v, 0) / recent.length;
            floor = Math.max(floor, recentAvg * 0.90);
        }
    }
    const floored = Math.max(raw, floor);
    return { value: Math.max(floored, 0), weatherSource: weather.source };
}

async function updateDashboard() {
    if (!metroData || metroData.length === 0) return;
    
    // 最新数据
    const latest = metroData[metroData.length - 1];
    
    // 设置默认日期
    selectDate(latest, { labelText: '较昨日' });
    
    // 显示预测
    updatePredictions();
        
        // 获取当前月份数据
        const currentMonth = latest.date.slice(0, 7); // "2026-03"
        const currentMonthData = metroData.filter(item => item.date.startsWith(currentMonth));
    
    // 本月最高
    if (currentMonthData.length > 0) {
        const maxItem = currentMonthData.reduce((max, item) => item.total > max.total ? item : max, currentMonthData[0]);
        document.getElementById('monthMax').textContent = maxItem.total.toFixed(1) + '万';
        document.getElementById('monthMaxDate').textContent = maxItem.date;
    }
    
    // 本月平均
    if (currentMonthData.length > 0) {
        const avg = currentMonthData.reduce((sum, item) => sum + item.total, 0) / currentMonthData.length;
        document.getElementById('monthAvg').textContent = avg.toFixed(1);
    }
    
    // 最后更新
    const displayDate = lastUpdated && lastUpdated.includes(' ') ? lastUpdated.split(' ')[0] : lastUpdated;
    updateLastUpdated(displayDate || latest.date);
}

function updatePredictions() {
    if (!metroData || metroData.length === 0) return;
    if (!regressionModel) {
        const todayEl = document.getElementById('predictedTotal');
        const todayNoteEl = document.getElementById('predictedChange');
        const tomorrowEl = document.getElementById('predictedTomorrowTotal');
        const tomorrowNoteEl = document.getElementById('predictedTomorrowNote');
        if (todayEl) todayEl.textContent = '--';
        if (todayNoteEl) todayNoteEl.textContent = '模型训练失败';
        if (tomorrowEl) tomorrowEl.textContent = '--';
        if (tomorrowNoteEl) tomorrowNoteEl.textContent = '模型训练失败';
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
    const todayNoteEl = document.getElementById('predictedChange');
    if (todayEl) {
        todayEl.textContent = todayResult ? todayResult.value.toFixed(1) + '万' : '--';
    }
    if (todayNoteEl) {
        const note = [];
        note.push(`预测日期 ${todayStr}`);
        if (todayResult && todayResult.weatherSource === 'avg7') {
            note.push('天气缺失，使用近7日均值');
        }
        if (hasActualToday) {
            note.push('今日已有实际数据');
        }
        if (!todayResult) {
            note.push('数据不足，无法预测');
        }
        todayNoteEl.textContent = note.join(' · ');
    }

    const tomorrowEl = document.getElementById('predictedTomorrowTotal');
    const tomorrowNoteEl = document.getElementById('predictedTomorrowNote');
    if (tomorrowEl) {
        tomorrowEl.textContent = tomorrowResult ? tomorrowResult.value.toFixed(1) + '万' : '--';
    }
    if (tomorrowNoteEl) {
        const note = [];
        note.push(`预测日期 ${tomorrowStr}`);
        if (tomorrowResult && tomorrowResult.weatherSource === 'avg7') {
            note.push('天气缺失，使用近7日均值');
        }
        if (!tomorrowResult) {
            note.push('数据不足，无法预测');
        }
        tomorrowNoteEl.textContent = note.join(' · ');
    }
}

// 初始化图表
function initCharts() {
    initTrendChart();
    initPieChart();
}

// 趋势图
function initTrendChart() {
    trendChart = echarts.init(document.getElementById('trendChart'));
    updateTrendChart();
    window.addEventListener('resize', () => trendChart.resize());

    // 添加点击事件
    trendChart.on('click', function(params) {
        if (params.componentType === 'series') {
            const clickedDate = params.name;
            const clickedData = [...metroData].reverse().find(item => item.date === clickedDate);
            if (clickedData) {
                selectDate(clickedData);
            }
        }
    });
}

// 更新趋势图数据
function updateTrendChart() {
    let filteredData = metroData;

    if (currentTrendRange === 'week') {
        filteredData = metroData.slice(-7);
    } else if (currentTrendRange === 'month') {
        filteredData = metroData.slice(-30);
    } else if (currentTrendRange === 'year') {
        filteredData = metroData.slice(-365);
    }

    const dates = filteredData.map(d => d.date);
    const values = filteredData.map(d => d.total);

    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: function(params) {
                const date = params[0].name;
                const value = params[0].value;
                return `${date}<br/>总客流: ${value}万`;
            }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            containLabel: true
        },
        dataZoom: [
            {
                type: 'inside',
                start: 0,
                end: 100
            },
            {
                type: 'slider',
                start: 0,
                end: 100,
                height: 20,
                bottom: 5,
                borderColor: 'transparent',
                backgroundColor: '#f0f0f0',
                fillerColor: 'rgba(59, 130, 246, 0.2)',
                handleStyle: {
                    color: '#3B82F6'
                }
            }
        ],
        xAxis: {
            type: 'category',
            data: dates,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: {
            type: 'value',
            name: '万人次',
            min: function(value) {
                return Math.floor(value.min - 10);
            }
        },
        series: [{
            data: values,
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 8,
            lineStyle: {
                color: '#3B82F6',
                width: 3
            },
            itemStyle: {
                color: '#3B82F6'
            },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                        { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
                        { offset: 1, color: 'rgba(59, 130, 246, 0.05)' }
                    ]
                }
            }
        }]
    };

    trendChart.setOption(option, true);
}

// 设置趋势图时间范围
function setTrendRange(range) {
    currentTrendRange = range;

    // 更新按钮样式
    document.getElementById('btn-all').className = range === 'all'
        ? 'px-3 py-1 text-sm rounded bg-blue-500 text-white'
        : 'px-3 py-1 text-sm rounded bg-gray-200 text-gray-700';
    document.getElementById('btn-month').className = range === 'month'
        ? 'px-3 py-1 text-sm rounded bg-blue-500 text-white'
        : 'px-3 py-1 text-sm rounded bg-gray-200 text-gray-700';
    document.getElementById('btn-week').className = range === 'week'
        ? 'px-3 py-1 text-sm rounded bg-blue-500 text-white'
        : 'px-3 py-1 text-sm rounded bg-gray-200 text-gray-700';
    document.getElementById('btn-year').className = range === 'year'
        ? 'px-3 py-1 text-sm rounded bg-blue-500 text-white'
        : 'px-3 py-1 text-sm rounded bg-gray-200 text-gray-700';

    updateTrendChart();
}

// 饼图
function initPieChart() {
    pieChart = echarts.init(document.getElementById('pieChart'));
    updatePieChart();
    window.addEventListener('resize', () => pieChart.resize());
}

function updatePieChart() {
    if (!metroData || metroData.length === 0 || !pieChart) return;
    const latest = selectedDateData || metroData[metroData.length - 1];
    const pieData = Object.entries(latest.lines)
        .map(([lineId, value]) => {
            const lineInfo = linesInfo.find(l => l.id === lineId);
            return {
                name: lineInfo ? lineInfo.name : lineId,
                value: value,
                itemStyle: { color: lineInfo ? lineInfo.color : '#999' }
            };
        })
        .sort((a, b) => b.value - a.value);

    const legendNames = pieData.map(item => item.name);
    const splitIndex = Math.ceil(legendNames.length / 2);
    const legendLeft = legendNames.slice(0, splitIndex);
    const legendRight = legendNames.slice(splitIndex);

    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c}万 ({d}%)'
        },
        legend: [
            {
                type: 'plain',
                selectedMode: false,
                orient: 'vertical',
                left: '60%',
                top: 20,
                itemGap: 8,
                textStyle: { fontSize: 11 },
                data: legendLeft
            },
            {
                type: 'plain',
                selectedMode: false,
                orient: 'vertical',
                left: '78%',
                top: 20,
                itemGap: 8,
                textStyle: { fontSize: 11 },
                data: legendRight
            }
        ],
        series: [{
            type: 'pie',
            radius: ['38%', '68%'],
            center: ['32%', '50%'],
            avoidLabelOverlap: false,
            itemStyle: {
                borderRadius: 6,
                borderColor: '#fff',
                borderWidth: 2
            },
            label: {
                show: false
            },
            emphasis: {
                label: {
                    show: true,
                    fontSize: 14,
                    fontWeight: 'bold'
                }
            },
            data: pieData
        }]
    };

    pieChart.setOption(option);
}

// 选择日期
function selectDate(data, options = {}) {
    selectedDateData = data;
    selectedDate = data.date;
    const labelText = options.labelText || '较前日';

    // 更新日期标签
    const dateLabel = document.getElementById('selectedDateLabel');
    const dateLabel2 = document.getElementById('selectedDateLabel2');
    if (dateLabel) {
        dateLabel.textContent = `${data.date}总客流`;
    }
    if (dateLabel2) {
        dateLabel2.textContent = `${data.date}各线路客流`;
    }
    const pieDateLabel = document.getElementById('pieDateLabel');
    if (pieDateLabel) {
        pieDateLabel.textContent = data.date;
    }

    // 更新总客流显示
    document.getElementById('todayTotal').textContent = data.total.toFixed(1) + '万';

    // 更新变化率（如果可能）
    if (metroData.length > 1) {
        const currentIndex = metroData.findIndex(item => item.date === data.date);
        const previous = currentIndex >= 0 ? metroData[currentIndex - 1] : null;
        updateChangeRate(data, previous, labelText);
    }

    // 重新渲染表格
    renderLinesTable();
    updatePieChart();
}

// 渲染线路表格
function renderLinesTable() {
    const tbody = document.getElementById('linesTable');
    const data = selectedDateData || metroData[metroData.length - 1];
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

    tbody.innerHTML = sortedLines.map(line => `
        <tr class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="line-badge" style="background-color: ${line.color}">
                    ${line.name}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-gray-900 font-medium">
                ${line.value.toFixed(1)}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-gray-500">
                ${line.percent}%
            </td>
        </tr>
    `).join('');
}
