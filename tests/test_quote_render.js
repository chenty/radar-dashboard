const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync('templates/index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const context = vm.createContext({
  console, URL, URLSearchParams,
  window: { addEventListener() {}, matchMedia: () => ({matches:false}) },
  document: {
    getElementById() { return null; },
    documentElement: {setAttribute() {}},
    createElement() { return { set textContent(v) {this.innerHTML=String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}, innerHTML:'' }; }
  },
  location: {search:'',hash:''}, localStorage: {getItem() {return null;},setItem() {}},
});
vm.runInContext(script, context);
vm.runInContext("favBtnHtml=()=>''; copyBtnHtml=()=>''; markFavorites=()=>{};", context);
const item = {quote:'真实原话', author:'说话者', source:'出处名称', topic:'成长', usage:'开头', url:'https://example.com/article'};
context.item = item;
let daily = vm.runInContext("renderModuleItem('quoteBank', item)", context);
for (const text of ['真实原话','说话者','出处名称','成长','开头','https://example.com/article']) assert(daily.includes(text), text);
assert(!daily.includes('未命名'));
context.items = [item, {text:'历史正文',speaker:'历史作者',source_url:'javascript:alert(1)',date:'2026-01-01'}];
vm.runInContext("api=async()=>items;", context);
const container = {innerHTML:''}; context.container = container;
(async()=>{
  await vm.runInContext("renderModule(container,'quotes')",context);
  for (const text of ['真实原话','说话者','出处名称','历史正文','历史作者']) assert(container.innerHTML.includes(text), text);
  assert(!container.innerHTML.includes('未命名'));
  assert(!container.innerHTML.includes('javascript:'));
  context.item = {title:'独立标题',quote:'独立原话',author:'作者',url:'https://example.com/"onmouseover="x'};
  daily = vm.runInContext("renderModuleItem('quoteBank', item)",context);
  assert(daily.includes('独立标题') && daily.includes('独立原话') && daily.includes('作者'));
  assert(!daily.includes('href="https://example.com/"onmouseover='));
  context.item = {title:'非金句标题',what:'做什么'};
  assert(vm.runInContext("renderModuleItem('signals', item)",context).includes('非金句标题'));
  console.log('quote rendering: ok');
})().catch(e => {console.error(e);process.exit(1)});
