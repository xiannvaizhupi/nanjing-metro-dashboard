// 测试解析功能
const testText = "26-3-9#昨日客流#南京地铁3月9日客运量328.3，其中1号线70.7，2号线55.9，3号线61.1，4号线18.1，5号线35.4，7号线28.9，10号线18.8，S1号线9.9，S3号线9.9，S6号线5.4，S7号线1.5，S8号线10.6，S9号线2.1（以上单位: 万）";

// 解析日期
function parseDate(text) {
    const patterns = [
        /(\d{2,4})[-/](\d{1,2})[-/](\d{1,2})/,
        /(\d{1,2})月(\d{1,2})[日号]/,
        /(\d{1,2})\.(\d{1,2})/,
    ];

    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            let year, month, day;
            
            if (match[0].includes('月')) {
                month = match[1].padStart(2, '0');
                day = match[2].padStart(2, '0');
                year = '2026';
            } else if (match[0].includes('.')) {
                month = match[1].padStart(2, '0');
                day = match[2].padStart(2, '0');
                year = '2026';
            } else {
                year = match[1].length === 2 ? '20' + match[1] : match[1];
                month = match[2].padStart(2, '0');
                day = match[3].padStart(2, '0');
            }
            
            return `${year}-${month}-${day}`;
        }
    }
    return null;
}

// 解析总客流
function parseTotal(text) {
    const patterns = [
        /客运量\s*(\d+\.?\d*)/,
        /总客流\s*(\d+\.?\d*)/,
        /客流\s*(\d+\.?\d*)\s*万/,
        /(\d+\.?\d*)\s*万人次/,
        /(\d+\.?\d*)\s*万/,
    ];

    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            return parseFloat(match[1]);
        }
    }
    return null;
}

// 解析各线路
function parseLines(text) {
    const lines = {};
    const linePattern = /([1-9]|10|S[1-9])[号号线线]?\s*(\d+\.?\d*)/g;
    
    let match;
    while ((match = linePattern.exec(text)) !== null) {
        let lineKey = match[1];
        const value = parseFloat(match[2]);
        
        if (lineKey.startsWith('S')) {
            lineKey = lineKey.toUpperCase();
        } else if (lineKey === '10') {
            lineKey = 'L10';
        } else {
            lineKey = 'L' + lineKey;
        }
        
        if (value > 0 && value < 500) {
            lines[lineKey] = value;
        }
    }
    
    return lines;
}

// 测试
console.log("测试文本:", testText);
console.log("\n解析结果:");
console.log("日期:", parseDate(testText));
console.log("总客流:", parseTotal(testText));
console.log("各线路:", parseLines(testText));

const lines = parseLines(testText);
const sum = Object.values(lines).reduce((a, b) => a + b, 0);
console.log("\n线路总和:", sum.toFixed(1));
console.log("与总客流差值:", (328.3 - sum).toFixed(1));
