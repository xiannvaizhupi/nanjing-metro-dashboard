// 主JavaScript文件
let metroData = null;
let linesInfo = null;
let trendChart = null;
let currentTrendRange = 'all';
let selectedDateData = null;
let selectedDate = null;

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

        // 显示最后更新时间
        const lastUpdateEl = document.getElementById('lastUpdate');
        if (lastUpdateEl) {
            lastUpdateEl.textContent = data.metadata.last_updated;
        }

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

// 更新仪表板数据
function updateDashboard() {
    if (!metroData || metroData.length === 0) return;
    
    // 最新数据
    const latest = metroData[0];
    const previous = metroData[1];
    
    // 设置默认日期
    selectDate(latest);
    
    // 环比变化
    if (previous) {
        const change = ((latest.total - previous.total) / previous.total * 100).toFixed(1);
        const changeEl = document.getElementById('todayChange');
        if (change > 0) {
            changeEl.innerHTML = `<span class="text-red-500">↗ +${change}%</span> 较昨日`;
        } else {
            changeEl.innerHTML = `<span class="text-green-500">↘ ${change}%</span> 较昨日`;
        }
    }
    
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
    document.getElementById('lastUpdate').textContent = latest.date;
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
            const clickedData = metroData.find(item => item.date.slice(5) === clickedDate);
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
        filteredData = metroData.slice(0, 7);
    } else if (currentTrendRange === 'month') {
        filteredData = metroData.slice(0, 30);
    }

    const dates = filteredData.map(d => d.date.slice(5)).reverse();
    const values = filteredData.map(d => d.total).reverse();

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
            bottom: '3%',
            containLabel: true
        },
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

    updateTrendChart();
}

// 饼图
function initPieChart() {
    const chart = echarts.init(document.getElementById('pieChart'));

    const latest = metroData[0];
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

    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c}万 ({d}%)'
        },
        legend: {
            type: 'scroll',
            orient: 'vertical',
            right: 10,
            top: 20,
            bottom: 20,
            textStyle: {
                fontSize: 11
            }
        },
        series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['35%', '50%'],
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

    chart.setOption(option);
    window.addEventListener('resize', () => chart.resize());
}

// 选择日期
function selectDate(data) {
    selectedDateData = data;
    selectedDate = data.date;

    // 更新日期标签
    const dateLabel = document.getElementById('selectedDateLabel');
    const dateLabel2 = document.getElementById('selectedDateLabel2');
    if (dateLabel) {
        dateLabel.textContent = `${data.date.slice(5)}总客流`;
    }
    if (dateLabel2) {
        dateLabel2.textContent = `🚇 ${data.date.slice(5)}各线路客流`;
    }

    // 更新总客流显示
    document.getElementById('todayTotal').textContent = data.total.toFixed(1) + '万';

    // 更新变化率（如果可能）
    if (metroData.length > 1) {
        const previousIndex = metroData.findIndex(item => item.date === data.date) - 1;
        if (previousIndex >= 0 && previousIndex < metroData.length) {
            const previous = metroData[previousIndex];
            const change = ((data.total - previous.total) / previous.total * 100).toFixed(1);
            const changeEl = document.getElementById('todayChange');
            if (changeEl) {
                if (change > 0) {
                    changeEl.innerHTML = `<span class="text-red-500">↗ +${change}%</span> 较前日`;
                } else {
                    changeEl.innerHTML = `<span class="text-green-500">↘ ${change}%</span> 较前日`;
                }
            }
        }
    }

    // 重新渲染表格
    renderLinesTable();
}

// 渲染线路表格
function renderLinesTable() {
    const tbody = document.getElementById('linesTable');
    const data = selectedDateData || metroData[0];
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

    const maxValue = sortedLines[0].value;

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
            <td class="px-6 py-4 whitespace-nowrap">
                <div class="progress-bar" style="width: 150px;">
                    <div class="progress-fill" style="width: ${(line.value / maxValue * 100).toFixed(1)}%; background-color: ${line.color}"></div>
                </div>
            </td>
        </tr>
    `).join('');
}