// --- DOM 요소 가져오기 ---
const analyzeBtn = document.getElementById('analyze-btn');
const resultArea = document.getElementById('result-area');
const siteSelect = document.getElementById('site');
const stockSelect = document.getElementById('stock');
const genAiSelect = document.getElementById('gen-ai');
const container = document.getElementById('table-container');
// 참고: HTML에 어떤 분석을 할지 선택하는 드롭다운이 필요합니다.
// 예: <select id="analysis-type"><option value="market">시장</option>...</select>
const analysisTypeSelect = document.getElementById('analysis-type');
// --- 백엔드 API 주소 ---
// 기본 URL만 정의하고, 전체 경로는 동적으로 생성합니다.
const baseUrl = '';

function transformData(data) {
    const headers = Object.keys(data);
    if (headers.length === 0) {
        return [];
    }
    const numRows = Object.keys(data[headers[0]]).length;
    const result = [];

    for (let i = 0; i < numRows; i++) {
        const row = {};
        headers.forEach(header => {
            row[header] = data[header][i.toString()];
        });
        result.push(row);
    }
    return result;
}

function jsonToHtmlTable(jsonString) {
    // 1. JSON 문자열을 JavaScript 객체로 파싱합니다.
    const json_data = JSON.parse(jsonString);

    // 데이터가 배열이 아니거나 비어있으면 빈 테이블을 반환합니다.
    if (!Array.isArray(json_data) || json_data.length === 0) {
        return document.createElement('table');
    }

    // 2. 테이블 관련 요소들을 생성하고 TailwindCSS 클래스를 팍팍 적용합니다.
    const table = document.createElement('table');
    table.className = 'w-full text-sm text-left text-gray-500';
    table.id = 'dataTable'; // 기존 스타일도 혹시 모르니 ID는 남겨두죠.

    const thead = document.createElement('thead');
    thead.className = 'text-xs text-gray-700 uppercase bg-gray-50';

    const tbody = document.createElement('tbody');
    const headerRow = document.createElement('tr');

    // 3. 테이블 헤더(th)를 생성합니다. (첫 번째 객체의 키를 사용)
    const headers = Object.keys(json_data[0]);
    headers.forEach(headerText => {
        const th = document.createElement('th');
        th.scope = 'col';
        th.className = 'px-6 py-3 border border-gray-200'; // 테두리 스타일 추가요!
        th.textContent = headerText;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // 4. 테이블 본문(td)을 생성합니다.
    json_data.forEach((obj, index) => {
        const row = document.createElement('tr');
        // 짝수 행에 배경색을 다르게 줍시다. 훨씬 보기 좋죠?
        row.className = index % 2 === 0 ? 'bg-white border-b' : 'bg-gray-50 border-b';

        headers.forEach(header => {
            const cell = document.createElement('td');
            cell.className = 'px-6 py-4 border border-gray-200'; // 여기도 테두리 스타일 추가요!
            // 값이 null이나 undefined일 경우 빈 문자열로 처리합니다.
            cell.textContent = obj[header] !== null && obj[header] !== undefined ? obj[header] : '';
            row.appendChild(cell);
        });
        tbody.appendChild(row);
    });

    table.appendChild(tbody);

    // 5. 완성된 테이블 요소를 반환합니다.
    return table;
}
// --- '분석' 버튼 클릭 이벤트 리스너 ---
analyzeBtn.addEventListener('click', async () => {
    // 1. 현재 선택된 값들을 가져옵니다.
    const analysisType = analysisTypeSelect.value; // 'market', 'fundamentals', 'news' 등
    const site = siteSelect.value;
    const stock = stockSelect.value;
    const genAi = genAiSelect.value; // GET 요청에서는 쿼리 파라미터로 사용할 수 있습니다.

    // 2. 버튼 비활성화 및 로딩 메시지 표시
    analyzeBtn.disabled = true;
    resultArea.innerHTML = '서버에 분석을 요청하는 중...';

    // RESTful API 엔드포인트에 맞게 URL을 동적으로 생성합니다.
    // gen_ai는 쿼리 문자열로 추가합니다.
    const requestUrl = `${baseUrl}/${analysisType}/${site}/${encodeURIComponent(stock)}?gen_ai=${genAi}`;
    
    try {
        // 3. Fetch API를 사용하여 백엔드에 GET 요청을 보냅니다.
        const response = await fetch(requestUrl); // POST에서 GET으로 변경

        // 4. 서버 응답을 JSON 형태로 파싱합니다.
        const data = await response.json();

        // 5. 응답 상태에 따라 결과를 처리합니다.
        if (!response.ok) {
            // FastAPI에서 보낸 에러 메시지(detail)를 표시합니다.
            throw new Error(data.detail || `HTTP error! status: ${response.status}`);
        }
        console.log("Response Data:", data);
        // 성공 시, 결과 텍스트 영역에 값을 표시합니다.
        // 결과가 객체나 배열일 수 있으므로 JSON.stringify를 사용하여 예쁘게 출력합니다.
        const jsonString = JSON.stringify(data.result, null, 2);
        resultArea.innerHTML = marked.parse(data.analysis); // 그냥 넣지 말고, marked.parse()로 감싸주기!
        container.innerHTML = '';
        // 함수를 호출하여 테이블 요소를 생성합니다.
        const newTable = jsonToHtmlTable(jsonString);
        // 생성된 테이블을 컨테이너에 추가합니다.
        container.appendChild(newTable);

    } catch (error) {
        // 에러 발생 시, 에러 메시지를 표시합니다.
        console.error("Fetch Error:", error);
        resultArea.innerHTML = `오류가 발생했습니다: ${error.message}`;
    } finally {
        // 6. 요청 완료 후 버튼을 다시 활성화합니다.
        analyzeBtn.disabled = false;
    }
});