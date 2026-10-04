const demoMatches = [
  {id:'a1',name:'林间来信',age:28,city:'杭州',emoji:'🌿',tags:['散步','阅读','认真沟通'],intro:'喜欢慢慢认识彼此，也愿意分享日常。'},
  {id:'a2',name:'海风有约',age:31,city:'宁波',emoji:'🌊',tags:['海边','电影','稳定关系'],intro:'希望以尊重和真诚为前提，寻找长期关系。'},
  {id:'a3',name:'晚灯',age:26,city:'上海',emoji:'🌙',tags:['音乐','猫','独立'],intro:'平时喜欢音乐和城市漫步，重视边界感。'},
  {id:'a4',name:'青山慢行',age:30,city:'成都',emoji:'⛰️',tags:['徒步','做饭','耐心'],intro:'喜欢户外活动，也享受安静的周末。'},
  {id:'a5',name:'晴窗',age:27,city:'北京',emoji:'☀️',tags:['展览','旅行','坦诚'],intro:'希望遇见能坦诚交流、彼此支持的人。'}
];

Page({
  data:{ageMin:18,ageMax:60,cities:['不限城市 · 随机匹配','杭州','宁波','上海','北京','成都'],cityIndex:0,visibleMatches:demoMatches.slice(0,2),shownCount:2,matchStarted:false,round:0},
  onLoad(){
    if(wx.getStorageSync('hepai_adult_demo')===true)return;
    wx.showModal({title:'仅限成年人体验',content:'这是演示原型，不包含实名或年龄核验。未满18岁请退出。',confirmText:'我已满18岁',cancelText:'退出',success:(res)=>{
      if(res.confirm)wx.setStorageSync('hepai_adult_demo',true);
      else wx.reLaunch({url:'/pages/me/index'});
    }});
  },
  onAgeMin(e){this.setData({ageMin:e.detail.value||18});},
  onAgeMax(e){this.setData({ageMax:e.detail.value||60});},
  onCityChange(e){this.setData({cityIndex:Number(e.detail.value)},()=>this.filterDemo());},
  filterDemo(){
    const min=Number(this.data.ageMin)||18, max=Number(this.data.ageMax)||60;
    const city=this.data.cities[this.data.cityIndex];
    let list=demoMatches.filter(x=>x.age>=min&&x.age<=max&&(this.data.cityIndex===0||x.city===city));
    if(list.length>1&&this.data.round){const shift=this.data.round%list.length;list=list.slice(shift).concat(list.slice(0,shift));}
    this.setData({visibleMatches:list.slice(0,2),shownCount:list.length});
  },
  onMatch(){
    this.setData({matchStarted:true,round:this.data.round+1},()=>{
      this.filterDemo();
      wx.showToast({title:'展示的是虚构演示资料',icon:'none'});
    });
  },
  onReport(){wx.showModal({title:'举报功能演示',content:'该演示不会提交举报，也不会触发审核或处罚。正式服务需接入可审计的审核和申诉流程。',showCancel:false});}
});

