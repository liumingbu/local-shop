const path=require('node:path');
const root=path.resolve(__dirname,'../../apps/miniprogram/dist');
const ids={
  'merchant-a':'00000000-0000-4000-8000-000000000001',
  'merchant-b':'00000000-0000-4000-8000-000000000002',
  'customer-a':'00000000-0000-4000-8000-000000000003',
  'customer-b':'00000000-0000-4000-8000-000000000004',
};
function setup(){
  const state={storage:new Map(),calls:[],navigation:[],downloads:[],env:'develop',storageFails:false,
    handler:()=>({status:200,data:{}}),chooseCancel:false,modalConfirm:false};
  global.wx={
    getAccountInfoSync:()=>({miniProgram:{envVersion:state.env}}),
    getStorageSync:key=>structuredClone(state.storage.get(key)),
    setStorageSync(key,value){if(state.storageFails)throw new Error('quota');state.storage.set(key,structuredClone(value));},
    navigateTo:args=>state.navigation.push(args.url),redirectTo:args=>state.navigation.push(args.url),
    showModal:args=>args.success?.({confirm:state.modalConfirm,cancel:!state.modalConfirm}),
    request(options){
      state.calls.push(options);
      queueMicrotask(async()=>{
        try{
          const pathname=new URL(options.url).pathname;
          let result;
          if(pathname==='/api/v1/dev/session')result={status:200,data:{access_token:`synthetic:${options.data.identity}`}};
          else if(pathname==='/api/v1/dev/me')result={status:200,data:{user_id:ids[(options.header.Authorization||'').split(':')[1]]}};
          else result=await state.handler(options);
          options.success({statusCode:result.status,data:result.data,header:{},cookies:[],errMsg:'ok'});
        }catch{options.fail({errMsg:'synthetic network failure'});}
      });return {abort(){}};
    },
    downloadFile(options){state.downloads.push(options);queueMicrotask(()=>options.success({statusCode:200,tempFilePath:'/synthetic/private-image.jpg'}));return{abort(){}};},
    chooseMedia(options){queueMicrotask(()=>state.chooseCancel?options.fail({errMsg:'cancel'}):options.success({tempFiles:[{tempFilePath:'/synthetic/source.jpg',size:8}]}));},
    compressImage(options){queueMicrotask(()=>options.success({tempFilePath:'/synthetic/compressed.jpg'}));},
    getFileSystemManager:()=>({readFile(options){options.success({data:new Uint8Array([255,216,255,217]).buffer});}}),
  };
  const client=require(path.join(root,'lib/client.js'));
  const {config}=require(path.join(root,'config.js'));
  client.logout();config.apiOrigin='http://127.0.0.1:8000';config.enableDevelopmentLogin=true;config.enableWechatLogin=false;
  return {state,client,config,drafts:require(path.join(root,'lib/drafts.js')),ui:require(path.join(root,'lib/ui.js'))};
}
function page(name){
  let options;global.Page=value=>{options=value;};
  const file=path.join(root,'pages',name,`${name}.js`);delete require.cache[require.resolve(file)];require(file);
  const instance={data:structuredClone(options.data),setData(value){Object.assign(this.data,structuredClone(value));}};
  for(const [name,value]of Object.entries(options)){if(name!=='data')instance[name]=typeof value==='function'?value.bind(instance):structuredClone(value);}
  return instance;
}
async function idle(instance){for(let i=0;i<200;i++){if(!instance.data.busy)return;await new Promise(resolve=>setTimeout(resolve,5));}throw new Error('Page stayed busy');}
function input(value,field,index){return {detail:{value},currentTarget:{dataset:{field,index}}};}
module.exports={setup,page,idle,input,root,ids};
