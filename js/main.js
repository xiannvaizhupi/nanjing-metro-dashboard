// 主JavaScript文件
let metroData = null;
let linesInfo = null;
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
        const response = await fetch('data/metro_data.json');
        const data = await response.json();
        metroData = data.daily_data;
        linesInfo = data.metadata.lines;

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

// 获取天气预报
async function getForecast() {
    try {
        const resp = await fetch('https://api.open-meteo.com/v1/forecast?latitude=32.06&longitude=118.79&daily=weathercode,precipitation_sum&timezone=Asia/Shanghai&forecast_days=2');
        const data = await resp.json();
        // 明天(索引1)的天气
        const tomorrowCode = data.daily.weathercode[1];
        const tomorrowPrecip = data.daily.precipitation_sum[1];
        
        // 判断天气类型 (WMO代码)
        // 0:晴, 1-3:多云, 45-48:雾, 51-67:雨, 71-77:雪, 80-82:阵雨, 95+:雷暴
        if (tomorrowCode >= 71) return { type: 'snow', factor: 0.82 };  // 雪天 -18%
        if (tomorrowCode >= 61) return { type: 'heavy_rain', factor: 0.90 };  // 大雨 -10%
        if (tomorrowCode >= 51) return { type: 'rain', factor: 0.93 };  // 雨 -7%
        if (tomorrowCode >= 45) return { type: 'fog', factor: 0.98 };  // 雾 -2%
        return { type: 'clear', factor: 1.0 };  // 晴天
    } catch(e) {
        return { type: 'unknown', factor: 1.0 };
    }
}

// 预测明天客流量
async function predictToday() {
    if (!metroData || metroData.length === 0) return null;
    
    // 获取明天日期
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    const dayOfWeek = tomorrow.getDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
    
    // 获取天气预报
    const forecast = await getForecast();
    
    // 1. 最近7天平均 (35%)
    let sum7 = 0, count7 = 0;
    for (let i = 1; i <= 7; i++) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const ds = d.toISOString().split('T')[0];
        const found = metroData.find(x => x.date === ds);
        if (found) { sum7 += found.total; count7++; }
    }
    const avg7 = count7 > 0 ? sum7 / count7 : 0;
    
    // 2. 最近30天平均 (25%)
    let sum30 = 0, count30 = 0;
    for (let i = 1; i <= 30; i++) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const ds = d.toISOString().split('T')[0];
        const found = metroData.find(x => x.date === ds);
        if (found) { sum30 += found.total; count30++; }
    }
    const avg30 = count30 > 0 ? sum30 / count30 : 0;
    
    // 3. 同星期历史均值 (20%)
    let weekdaySum = 0, weekdayCount = 0;
    metroData.forEach(d => {
        const dDate = new Date(d.date);
        if (dDate.getDay() === dayOfWeek) {
            weekdaySum += d.total;
            weekdayCount++;
        }
    });
    const weekdayAvg = weekdayCount > 0 ? weekdaySum / weekdayCount : 0;
    
    // 4. 月份因素 (10%)
    const month = tomorrow.getMonth() + 1;
    const monthFactors = {1:0.90, 2:0.88, 3:1.00, 4:1.02, 5:0.98, 6:0.95, 7:0.93, 8:1.02, 9:0.98, 10:1.03, 11:1.06, 12:1.02};
    const monthFactor = monthFactors[month] || 1.0;
    
    // 5. 天气因素 (10%) - 根据天气预报
    const weatherFactor = forecast.factor;
    
    // 6. 趋势因子 (5%)
    const recentAvg = avg7;
    const overallAvg = avg30 || recentAvg;
    const trendFactor = recentAvg > overallAvg ? 1.02 : (recentAvg < overallAvg ? 0.98 : 1.0);
    
    // 综合计算
    let prediction = avg7 * 0.35 + avg30 * 0.25 + weekdayAvg * 0.20 + overallAvg * 0.10 * monthFactor + overallAvg * 0.05 * trendFactor;
    
    // 周末折扣 + 天气折扣
    if (isWeekend) prediction *= 0.93;
    prediction *= weatherFactor;
    
    // 显示天气预报
    const weatherEl = document.getElementById('predictedChange');
    if (weatherEl) {
        const weatherText = { snow: '❄️ 雪天', heavy_rain: '🌧️ 大雨', rain: '🌧️ 小雨', fog: '🌫️ 雾', clear: '☀️ 晴天', unknown: '未知' };
        weatherEl.textContent = '明天' + (weatherText[forecast.type] || '未知天气');
    }
    
    return prediction > 0 ? prediction : null;
}

// 更新仪表板数据
async function updateDashboard() {
    if (!metroData || metroData.length === 0) return;
    
    // 最新数据
    const latest = metroData[metroData.length - 1];
    
    // 设置默认日期
    selectDate(latest, { labelText: '较昨日' });
    
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
        
        // 显示预测
        const predicted = await predictToday();
        const predEl = document.getElementById('predictedTotal');
        if (predEl && predicted) {
            predEl.textContent = predicted.toFixed(1) + '万';
        }
}
