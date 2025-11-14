// ข้อมูล Zone และสาขาที่อยู่ใน Zone (ตัวอย่าง)
// Area Manager สามารถแก้ไขไฟล์นี้เพื่อกำหนด Zone ของตัวเอง

const ZONES_DATA = [
    {
        zone_id: "ZONE_BKK_CENTRAL",
        zone_name: "กรุงเทพ - ใจกลางเมือง",
        branch_ids: [1, 2, 3, 8, 9, 12, 19, 22] // ตัวอย่าง: สาขาในกรุงเทพกลาง
    },
    {
        zone_id: "ZONE_BKK_EAST",
        zone_name: "กรุงเทพ - ฝั่งตะวันออก",
        branch_ids: [9, 18] // Paradise Park, Central Bangna
    },
    {
        zone_id: "ZONE_BKK_WEST",
        zone_name: "กรุงเทพ - ฝั่งตะวันตก",
        branch_ids: [16, 17, 23] // Central Rama2, The Mall Bangkae, The Mall Thapra
    },
    {
        zone_id: "ZONE_BKK_NORTH",
        zone_name: "กรุงเทพ - ฝั่งเหนือ/ปริมณฑล",
        branch_ids: [1, 3, 6, 12, 20, 22] // Rangsit, Laksi, Future Park, Chaengwattana
    },
    {
        zone_id: "ZONE_EAST",
        zone_name: "ภาคตะวันออก",
        branch_ids: [4, 5, 11, 25] // Chonburi, Rayong, Bangsaen, Pattaya
    },
    {
        zone_id: "ZONE_CENTRAL",
        zone_name: "ภาคกลาง",
        branch_ids: [7] // Huahin
    },
    {
        zone_id: "ZONE_SOUTH",
        zone_name: "ภาคใต้",
        branch_ids: [10] // Samui
    },
    {
        zone_id: "ZONE_NORTHEAST",
        zone_name: "ภาคตะวันออกเฉียงเหนือ",
        branch_ids: [14, 15] // Khonkaen
    }
];

// ฟังก์ชันช่วยเหลือ
const ZoneHelper = {
    // ดึงรายชื่อสาขาทั้งหมดใน Zone
    getBranchesByZone: function(zoneId) {
        const zone = ZONES_DATA.find(z => z.zone_id === zoneId);
        if (!zone) return [];
        
        // ดึงข้อมูลสาขาจาก BRANCHES_DATA
        if (typeof BRANCHES_DATA === 'undefined') return [];
        
        return BRANCHES_DATA.filter(branch => 
            zone.branch_ids.includes(branch.branch_id)
        );
    },
    
    // ดึง branch_ids ทั้งหมดใน Zone (สำหรับส่งไป API)
    getBranchIdsByZone: function(zoneId) {
        const zone = ZONES_DATA.find(z => z.zone_id === zoneId);
        return zone ? zone.branch_ids : [];
    },
    
    // ดึงข้อมูล Zone ทั้งหมด
    getAllZones: function() {
        return ZONES_DATA;
    },
    
    // หา Zone ที่สาขานั้นอยู่
    getZonesByBranch: function(branchId) {
        return ZONES_DATA.filter(zone => 
            zone.branch_ids.includes(parseInt(branchId))
        );
    }
};

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ZONES_DATA, ZoneHelper };
}
