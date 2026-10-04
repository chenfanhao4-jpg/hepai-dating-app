const demoMatches = [
  {id:'a1',name:'林间来信',age:28,city:'杭州',emoji:'🌿',tags:['散步','阅读','认真沟通'],intro:'喜欢慢慢认识彼此，也愿意分享日常。'},
  {id:'a2',name:'海风有约',age:31,city:'宁波',emoji:'🌊',tags:['海边','电影','稳定关系'],intro:'希望以尊重和真诚为前提，寻找长期关系。'},
  {id:'a3',name:'晚灯',age:26,city:'上海',emoji:'🌙',tags:['音乐','猫','独立'],intro:'平时喜欢音乐和城市漫步，重视边界感。'},
  {id:'a4',name:'青山慢行',age:30,city:'成都',emoji:'⛰️',tags:['徒步','做饭','耐心'],intro:'喜欢户外活动，也享受安静的周末。'},
  {id:'a5',name:'晴窗',age:27,city:'北京',emoji:'☀️',tags:['展览','旅行','坦诚'],intro:'希望遇见能坦诚交流、彼此支持的人。'}
];

function localDay(){
  const d=new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

Page({
  data:{ageMin:18,ageMax:60,cities:['不限城市 · 随机匹配','杭州','宁波','上海','北京','成都'],cityIndex:0,visibleMatches:demoMatches.slice(0,2),shownCount:2,remaining:10,round:0},
  onLoad(){
    if(wx.getStorageSync('hepai_adult_demo')!==true){
      wx.showModal({title:'仅限成年人体验',content:'这是演示原型，不包含实名或年龄核验。未满18岁请退出。',confirmText:'我已满18岁',cancelText:'退出',success:(res)=>{
        if(res.confirm)wx.setStorageSync('hepai_adult_demo',true);
        else wx.reLaunch({url:'/pages/me/index'});
      }});
    }
  },
  onShow(){
    const usage=wx.getStorageSync('hepai_match_usage')||{};
    const used=usage.day===localDay()?Number(usage.used)||0:0;
    this.setData({remaining:Math.max(0,10-used)});
  },
  onAgeMin(e){this.setData({ageMin:e.detail.value||18},()=>this.filterDemo());},
  onAgeMax(e){this.setData({ageMax:e.detail.value||60},()=>this.filterDemo());},
  onCityChange(e){this.setData({cityIndex:Number(e.detail.value)},()=>this.filterDemo());},
  filterDemo(){
    const min=Number(this.data.ageMin)||18, max=Number(this.data.ageMax)||60;
    const city=this.data.cities[this.data.cityIndex];
    let list=demoMatches.filter(x=>x.age>=min&&x.age<=max&&(this.data.cityIndex===0||x.city===city));
    if(list.length>1&&this.data.round){const shift=this.data.round%list.length;list=list.slice(shift).concat(list.slice(0,shift));}
    this.setData({visibleMatches:list.slice(0,2),shownCount:list.length});
  },
  onMatch(){
    if(this.data.remaining<=0){wx.showToast({title:'今日演示次数已用完',icon:'none'});return;}
    if(this.data.shownCount===0){wx.showToast({title:'当前筛选下没有演示资料',icon:'none'});return;}
    const usage=wx.getStorageSync('hepai_match_usage')||{};
    const used=(usage.day===localDay()?Number(usage.used)||0:0)+1;
    wx.setStorageSync('hepai_match_usage',{day:localDay(),used});
    this.setData({remaining:Math.max(0,10-used),round:this.data.round+1},()=>{
      this.filterDemo();
      wx.showToast({title:'已切换演示资料，不是真人匹配',icon:'none',duration:2200});
    });
  },
  onLike(e){wx.showModal({title:'演示功能',content:`“${e.currentTarget.dataset.name}”是虚构资料，招呼没有发送。真实私聊尚未接入。`,showCancel:false});},
  onReport(e){wx.showModal({title:'举报入口演示',content:`当前不会提交对“${e.currentTarget.dataset.name}”的举报。真实审核与申诉服务尚未接入。`,showCancel:false});}
});
