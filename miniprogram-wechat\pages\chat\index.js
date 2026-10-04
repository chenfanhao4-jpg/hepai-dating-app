const blocked=['违法','犯罪','黄赌毒','色情','黄色','赌博','毒品','约炮','一夜情','裸聊','性交易'];
Page({
  data:{draft:'',messages:[]},
  onInput(e){this.setData({draft:e.detail.value});},
  onSend(){
    const text=(this.data.draft||'').trim();
    if(!text)return;
    const normalized=text.toLowerCase().replace(/[\s\W_]+/g,'');
    if(blocked.some(x=>normalized.includes(x))){
      this.setData({messages:this.data.messages.concat([{id:Date.now(),role:'assistant',text:'警告：该问题涉及产品禁止内容，我拒绝回答。普通约会和健康关系话题可以聊。'}]),draft:''});
      return;
    }
    wx.showToast({title:'AI 服务尚未接入，消息未发送',icon:'none',duration:2500});
    this.setData({draft:''});
  }
});

