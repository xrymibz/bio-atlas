App({
  onLaunch() {
    // 初始化本地数据
    const habits = wx.getStorageSync('habits') || []
    if (habits.length === 0) {
      // 默认示例习惯
      wx.setStorageSync('habits', [
        { id: 1, name: '早起', emoji: '🌅', records: [], created: '2026-03-01' },
        { id: 2, name: '喝水', emoji: '💧', records: [], created: '2026-03-01' },
        { id: 3, name: '运动', emoji: '🏃', records: [], created: '2026-03-01' }
      ])
    }
  }
})
