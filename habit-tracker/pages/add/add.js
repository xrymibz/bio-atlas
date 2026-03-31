Page({
  data: {
    name: '',
    emoji: '🌱',
    emojis: ['🌱', '🌅', '💧', '🏃', '📚', '🎯', '💪', '🧘', '🏋️', '🚴', '✍️', '🎨', '🎵', '😴', '🥗', '🍎']
  },

  onNameInput(e) {
    this.setData({ name: e.detail.value })
  },

  onEmojiSelect(e) {
    this.setData({ emoji: e.currentTarget.dataset.emoji })
  },

  addHabit() {
    const { name, emoji } = this.data

    if (!name.trim()) {
      wx.showToast({ title: '请输入习惯名称', icon: 'none' })
      return
    }

    const habits = wx.getStorageSync('habits') || []
    const newHabit = {
      id: Date.now(),
      name: name.trim(),
      emoji: emoji,
      records: [],
      created: this.formatDate(new Date())
    }

    habits.push(newHabit)
    wx.setStorageSync('habits', habits)

    wx.showToast({ title: '添加成功 🎉', icon: 'success' })

    setTimeout(() => {
      wx.switchTab({ url: '/pages/index/index' })
    }, 1500)
  },

  formatDate(date) {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
})
