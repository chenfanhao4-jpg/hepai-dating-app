Page({
  data:{step:-1,steps:[
    {scene:'末班车刚进站，站台只剩下你们两个人。广播说列车临时停运。',left:'一起查看站内公告',right:'先找工作人员确认'},
    {scene:'附近便利店还亮着灯，雨也小了一些。',left:'买两杯热饮等雨停',right:'规划一段有灯的步行路线'},
    {scene:'故事暂告一段落。现实里，舒服的相处也可以从一次真诚的交流开始。',left:'聊聊你会怎么选',right:'换个话题继续认识'}
  ],lastChoice:''},
  onStart(){this.setData({step:0,lastChoice:''});},
  onChoose(e){
    const choice=e.currentTarget.dataset.choice;
    const next=this.data.step+1;
    this.setData({step:Math.min(next,this.data.steps.length-1),lastChoice:choice});
    wx.showToast({title:'已记录本机演示选择',icon:'none'});
  },
  onReset(){this.setData({step:-1,lastChoice:''});}
});
