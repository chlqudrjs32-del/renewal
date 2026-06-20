// 동적 기능들을 위한 JavaScript 코드

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', function() {
    console.log('체육관 회원관리 시스템 로드됨');
    initPhonePartInputs();
    
    // 날짜 포맷 함수
    window.formatDate = function(dateString) {
        const date = new Date(dateString);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };
    
    // 오늘 날짜 가져오기
    window.getTodayDate = function() {
        return new Date().toISOString().split('T')[0];
    };
    
    // 날짜 비교 함수
    window.compareDates = function(date1, date2) {
        const d1 = new Date(date1);
        const d2 = new Date(date2);
        return d1 - d2;
    };
});

// 확인 창 표시
function confirmAction(message) {
    return confirm(message);
}

// 알림 표시
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    
    const container = document.querySelector('main');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        // 3초 후 자동 제거
        setTimeout(() => {
            alertDiv.remove();
        }, 3000);
    }
}

// 테이블 행 강조 함수
function highlightRow(rowElement) {
    rowElement.style.backgroundColor = '#fff3cd';
    setTimeout(() => {
        rowElement.style.backgroundColor = '';
    }, 1000);
}

// 테이블 검색 함수
function filterTable(tableId, searchInputId) {
    const searchInput = document.getElementById(searchInputId);
    if (!searchInput) return;
    
    const filter = searchInput.value.toLowerCase();
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
    });
}

// CSV 내보내기 함수
function exportTableToCSV(tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('th, td');
        const rowData = Array.from(cells).map(cell => 
            '"' + cell.textContent.trim().replace(/"/g, '""') + '"'
        );
        csv.push(rowData.join(','));
    });
    
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + csv.join('\n');
    const link = document.createElement('a');
    link.setAttribute('href', encodeURI(csvContent));
    link.setAttribute('download', filename || 'export.csv');
    link.click();
}

// 날짜 범위 계산
function getDaysBetween(date1, date2) {
    const d1 = new Date(date1);
    const d2 = new Date(date2);
    const timeDiff = Math.abs(d2 - d1);
    return Math.ceil(timeDiff / (1000 * 3600 * 24));
}

// 반복 제출 방지
function preventDoubleSubmit(formElement) {
    formElement.addEventListener('submit', function() {
        const submitButton = formElement.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = '처리 중...';
        }
    });
}

// 모든 폼에 반복 제출 방지 적용
document.querySelectorAll('form').forEach(form => {
    preventDoubleSubmit(form);
});

// 키보드 단축키 (Escape로 모달 닫기)
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        // 필요시 열린 모달이 있으면 닫기
    }
});

// 온라인/오프라인 상태 감시
window.addEventListener('online', function() {
    showAlert('인터넷 연결 복구됨', 'success');
});

window.addEventListener('offline', function() {
    showAlert('인터넷 연결이 끊어졌습니다', 'danger');
});

function initPhonePartInputs() {
    document.querySelectorAll('.phone-part').forEach(function(input) {
        input.addEventListener('input', function() {
            this.value = this.value.replace(/\D/g, '').slice(0, 4);
            if (this.value.length === 4) {
                const group = this.closest('.phone-input-group');
                const parts = group ? group.querySelectorAll('.phone-part') : [];
                if (parts[0] === this && parts[1]) {
                    parts[1].focus();
                }
            }
        });

        input.addEventListener('keydown', function(event) {
            if (event.key !== 'Backspace' || this.value.length > 0) {
                return;
            }
            const group = this.closest('.phone-input-group');
            const parts = group ? group.querySelectorAll('.phone-part') : [];
            if (parts[1] === this && parts[0]) {
                parts[0].focus();
            }
        });
    });
}
