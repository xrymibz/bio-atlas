const app = getApp()

Page({
  data: {
    habits: [],
    today: '',
    weekDays: ['日', '一', '二', '三', '四', '五', '六']
  },

  onShow() {
    this.setData({ today: this.formatDate(new Date()) })
    this.loadHabits()
  },

  loadHabits() {
    const habits = wx.getStorageSync('habits') || []
    const today = this.formatDate(new Date())

    // 计算连续打卡天数
    habits.forEach(habit => {
      let streak = 0
      const dates = habit.records || []

      // 从今天往前检查
      let checkDate = new Date()
      for (let i = 0; i < 365; i++) {
        const dateStr = this.formatDate(checkDate)
        if (dates.includes(dateStr)) {
          streak++
          checkDate.setDate(checkDate.getDate() - 1)
        } else {
          break
        }
      }

      habit.streak = streak
      habit.checkedToday = dates.includes(today)
    })

    this.setData({ habits })
  },

  formatDate(date) {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  },

  checkIn(e) {
    const id = e.currentTarget.dataset.id
    const habits = wx.getStorageSync('habits') || []
    const today = this.formatDate(new Date())

    const habit = habits.find(h => h.id === id)
    if (!habit) return

    if (!habit.records) habit.records = []

    if (habit.records.includes(today)) {
      wx.showToast({ title: '今日已打卡~', icon: 'success' })
      return
    }

    habit.records.push(today)
    wx.setStorageSync('habits', habits)

    this.loadHabits()
    wx.showToast({ title: '打卡成功 🎉', icon: 'success' })
  },

  deleteHabit(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '确认删除',
      content: '确定要删除这个习惯吗？',
      success: (res) => {
        if (res.confirm) {
          let habits = wx.getStorageSync('habits') || []
          habits = habits.filter(h => h.id !== id)
          wx.setStorageSync('habits', habits)
          this.loadHabits()
          wx.showToast({ title: '已删除', icon: 'success' })
        }
      }
    })
  }
})
