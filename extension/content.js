// รับข้อความจาก extension popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'setSessionId') {
        // บันทึก Session ID ลง localStorage
        localStorage.setItem('sessionId', request.sessionId);
        
        // แจ้งเตือนผู้ใช้
        showNotification('✅ อัพเดท Session ID สำเร็จ!');
        
        // ถ้ามี modal ตั้งค่าเปิดอยู่ ให้อัพเดทค่าใน input
        const sessionInput = document.getElementById('settingSessionId');
        if (sessionInput) {
            sessionInput.value = request.sessionId;
        }
        
        sendResponse({success: true});
    }
    return true;
});

// ฟังก์ชันแสดงการแจ้งเตือน
function showNotification(message) {
    // สร้าง notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #28a745;
        color: white;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        z-index: 10000;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 16px;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    
    // เพิ่ม animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(notification);
    
    // ลบหลัง 3 วินาที
    setTimeout(() => {
        notification.style.animation = 'slideIn 0.3s ease-out reverse';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// ตรวจสอบและแสดงสถานะ Session ID เมื่อโหลดหน้า
window.addEventListener('load', () => {
    const sessionId = localStorage.getItem('sessionId');
    if (sessionId) {
        console.log('✅ Session ID พร้อมใช้งาน');
    } else {
        console.log('⚠️ ยังไม่มี Session ID - กรุณาใช้ Extension เพื่อดึงข้อมูล');
    }
});
