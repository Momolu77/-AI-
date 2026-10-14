<script>
(() => {
  'use strict';
  const run = __RUN__, channel = __CHANNEL__, bridgeLines = __BRIDGE_LINES__;
  const producer = 'iframe-' + crypto.randomUUID();
  let phase = 'load', seq = 0, pendingClick = null;
  const registered = new WeakSet(), values = new WeakMap(), composing = new WeakSet();
  const originalListen = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, handler, options) {
    if (type === 'click' && this instanceof Element && !this.matches('html,body')) registered.add(this);
    return originalListen.call(this, type, handler, options);
  };
  const stringify = value => { try { return typeof value === 'string' ? value : JSON.stringify(value); } catch { return String(value); } };
  function packet(kind, extra = {}) {
    const id = crypto.randomUUID(), raw = new Date().toISOString();
    return {app:'teaching-preview', run_id:run, channel, kind, event_id:id, message_id:id, occurred_at:raw,
      transport:{producer_id:producer,producer_seq:++seq,raw_time:raw,monotonic_ms:performance.now(),clock_calibration_id:null,time_source:'iframe_clock',action_id:id,causal_parent_ids:[]}, ...extra};
  }
  const send = data => parent.postMessage(data, '*');
  const post = (kind, extra) => send(packet(kind, extra));
  for (const kind of ['log','warn','error']) {
    const original = console[kind].bind(console);
    console[kind] = (...args) => { original(...args);post(kind,{text:args.map(stringify).join(' ').slice(0,20000),error_type:'console.'+kind,error_phase:phase}); };
  }
  addEventListener('error', event => {
    const line = event.lineno > bridgeLines ? event.lineno - bridgeLines : null;
    post('error',{text:String(event.message||'Resource load error').slice(0,20000),error_type:event.error?.name||'Error',error_phase:phase,line,column:line && line>1 ? event.colno||null : null,stack:event.error?.stack||null});
  });
  addEventListener('unhandledrejection', event => post('error',{text:String(event.reason?.message||event.reason).slice(0,20000),error_type:'UnhandledRejection',error_phase:phase,stack:event.reason?.stack||null}));
  function describe(target) { return {tag:target.tagName.toLowerCase(),id:target.id||null,role:target.getAttribute('role'),label:(target.getAttribute('aria-label')||target.textContent||'').trim().slice(0,500)}; }
  function interaction(target, type) {phase='interaction';return packet('interaction',{interaction_type:type,target:describe(target),outcome:target.dataset.outcome||null,outcome_source:target.dataset.outcome?'artifact':'unknown'});}
  function control(event) {return event.target?.closest?.('input,textarea,select,[contenteditable=true]');}
  const value = target => target.isContentEditable ? target.textContent : target.value;
  addEventListener('focusin', event => {const target=control(event);if(target && !values.has(target))values.set(target,value(target));},true);
  addEventListener('compositionstart', event => {const target=control(event);if(target)composing.add(target);},true);
  addEventListener('compositionend', event => {const target=control(event);if(target)composing.delete(target);},true);
  function commit(event) {
    const target=control(event);
    if(!event.isTrusted || !target || composing.has(target) || target.matches('input[type=password]'))return;
    const selectable=target.matches('select,input[type=checkbox],input[type=radio],input[type=range]');
    if(selectable && event.type!=='change')return;
    const current=target.matches('input[type=checkbox],input[type=radio]')?target.checked:value(target);
    if(values.get(target)===current)return;
    values.set(target,current);send(interaction(target,selectable?'change':'input_commit'));
  }
  addEventListener('change',commit,true);addEventListener('blur',commit,true);
  addEventListener('click',event=>{
    if(!event.isTrusted)return;
    let target=event.target instanceof Element?event.target:null;
    while(target && !target.matches('button,a,[role=button],[role=option],input[type=button],input[type=submit],canvas,[onclick]') && !registered.has(target))target=target.parentElement;
    if(!target || target.matches('body,html') || event.target?.matches?.('select,input[type=checkbox],input[type=radio],input[type=range]'))return;
    const candidate={data:interaction(target,'activate'),form:target.form,cancelled:false};pendingClick=candidate;
    setTimeout(()=>{if(!candidate.cancelled)send(candidate.data);if(pendingClick===candidate)pendingClick=null;},0);
  },true);
  addEventListener('submit',event=>{if(!event.isTrusted)return;if(pendingClick?.form===event.target)pendingClick.cancelled=true;send(interaction(event.target,'submit'));},true);
  addEventListener('load',()=>{post('ready');phase='interaction';},{once:true});
})();
</script>
