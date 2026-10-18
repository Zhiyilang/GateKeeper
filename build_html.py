#!/usr/bin/env python3
"""GATEKEEPER single-file HTML generator.

Reads bank.json (produced by build_bank.py from the live AgentGuard engine)
and emits a self-contained index.html - no network, no external assets, opens
straight from disk. The embedded data is the *only* copy the game reads, so the
playable demo can never drift from the question bank.

Scoring mirrors demo.py exactly:
  correct -> score_right + (catch_bonus if engine was wrong)
  wrong   -> penalty_wrong[kind]

Baselines (release-everything / obey-engine / perfect) are recomputed in JS
from the same embedded bank, so the on-screen comparison is always consistent
with the numbers printed by demo.py and claimed in the README.

stdlib only. Deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_ACTION_ZH = {"release": "放行", "redact": "脱敏", "block": "拦截"}
_ACTION_EN = {"release": "RELEASE", "redact": "REDACT", "block": "BLOCK"}


def main() -> int:
    bank = json.loads((_HERE / "bank.json").read_text(encoding="utf-8"))
    data_js = json.dumps(bank, ensure_ascii=False, separators=(",", ":"))

    html = _TEMPLATE.replace("/*__BANK__*/", data_js)
    (_HERE / "index.html").write_text(html, encoding="utf-8")
    print("wrote index.html (%d bytes, %d questions)"
          % (len(html.encode("utf-8")), len(bank["questions"])))
    return 0


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GATEKEEPER - AI 网关值班员</title>
<style>
  :root{
    --bg:#0a0e14; --panel:#111824; --panel2:#0d141e; --line:#1e2a3a;
    --ink:#e6edf3; --dim:#8b9bb0; --accent:#39d3ff; --warn:#ffb454;
    --bad:#ff5c6c; --good:#4ade80; --mid:#a78bfa;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{background:var(--bg);color:var(--ink);
    font-family:"Segoe UI",system-ui,-apple-system,"Microsoft YaHei",sans-serif;
    display:flex;justify-content:center;padding:20px}
  .wrap{width:100%;max-width:760px}
  h1{font-size:22px;letter-spacing:1px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin-bottom:18px;line-height:1.6}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:22px;margin-bottom:16px}
  .bar{display:flex;justify-content:space-between;align-items:center;
    font-size:13px;color:var(--dim);margin-bottom:14px}
  .bar b{color:var(--accent);font-size:15px}
  .req{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--accent);
    border-radius:8px;padding:16px;font-size:15px;line-height:1.7;min-height:64px;
    white-space:pre-wrap;word-break:break-word}
  .acts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}
  button.act{border:1px solid var(--line);background:#16202e;color:var(--ink);
    padding:14px 8px;border-radius:10px;font-size:15px;cursor:pointer;transition:.12s}
  button.act:hover{border-color:var(--accent);transform:translateY(-2px)}
  button.act small{display:block;color:var(--dim);font-size:11px;margin-top:3px}
  button.primary{background:var(--accent);color:#04121a;border:none;font-weight:700;
    padding:12px 22px;border-radius:10px;cursor:pointer;font-size:15px}
  button.ghost{background:transparent;border:1px solid var(--line);color:var(--dim);
    padding:12px 22px;border-radius:10px;cursor:pointer}
  .feedback{margin-top:16px;border-top:1px dashed var(--line);padding-top:16px;
    font-size:14px;line-height:1.7;display:none}
  .fb-row{display:flex;gap:10px;margin:4px 0;align-items:center}
  .tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;
    font-weight:700;letter-spacing:.5px}
  .t-right{background:rgba(74,222,128,.15);color:var(--good)}
  .t-wrong{background:rgba(255,92,108,.15);color:var(--bad)}
  .t-catch{background:rgba(167,139,250,.18);color:var(--mid)}
  .delta{font-size:18px;font-weight:800;margin-left:auto}
  .pos{color:var(--good)} .neg{color:var(--bad)}
  .hidden{display:none!important}
  .center{text-align:center}
  .verdict{font-size:26px;font-weight:800;margin:8px 0}
  table.cmp{width:100%;border-collapse:collapse;margin-top:12px;font-size:14px}
  table.cmp td,table.cmp th{border:1px solid var(--line);padding:8px 10px;text-align:left}
  table.cmp th{color:var(--dim);font-weight:600}
  .me{color:var(--accent);font-weight:800}
  .tips{color:var(--dim);font-size:13px;line-height:1.7;margin-top:14px}
  .tips b{color:var(--warn)}
  .eng{color:var(--dim);font-size:12px}
  @media(max-width:520px){.acts{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap" id="root"></div>
<script>
const BANK = /*__BANK__*/;
const AZ = {release:"放行", redact:"脱敏", block:"拦截"};
const DAY_NAMES = {1:"第 1 天 · 直白注入",2:"第 2 天 · 角色扮演",3:"第 3 天 · 凭据与数据",
  4:"第 4 天 · 日常流量",5:"第 5 天 · 边界与误报",6:"第 6 天 · 混合攻击",7:"第 7 天 · 终极考核"};

// ---- baseline computation (mirrors demo.py) ----
function play(policy){
  let score=0, caught=0, missed=0, fb=0;
  for(const q of BANK.questions){
    let a;
    if(policy==="release") a="release";
    else if(policy==="obey") a=q.engine_action;
    else a=q.truth_action;
    if(a===q.truth_action){
      score += q.score_right;
      if(!q.engine_agrees){ score += q.catch_bonus; caught++; }
    } else {
      score += q.penalty_wrong;
      if(q.kind==="attack") missed++;
      if(q.kind==="benign") fb++;
    }
  }
  return {score, caught, missed, fb};
}
const BASE = {release:play("release"), obey:play("obey"), perfect:play("perfect")};

let state = {i:0, score:0, caught:0, right:0, wrong:0, log:[]};
const qs = BANK.questions.slice().sort((a,b)=> a.day-b.day || a.id.localeCompare(b.id));

function el(html){ const d=document.createElement("div"); d.innerHTML=html; return d.firstElementChild; }

function renderStart(){
  const r=el(`<div class="card center">
    <h1>GATEKEEPER</h1>
    <div class="sub" style="text-align:left">
      你是 AI 网关的值班员。每一份请求到达时，网关会给你一个<strong>建议</strong>——
      但它在 <strong style="color:var(--bad)">${BANK.questions.filter(q=>!q.engine_agrees).length}</strong> 个地方是<strong>错的</strong>。<br><br>
      你的分数来自<strong style="color:var(--accent)">纠正它</strong>，而不是盲从它。<br>
      三个动作：<b style="color:var(--good)">放行</b> 让请求通过 ·
      <b style="color:var(--warn)">脱敏</b> 遮掉敏感字段后通过 ·
      <b style="color:var(--bad)">拦截</b> 直接拒绝。<br><br>
      误杀正当流量扣分最重（${BANK.scoring.penalty_wrong.benign} 分）。拦截攻击、纠正网关误判有奖励。<br>
      共 ${qs.length} 份请求，跨越 7 天，难度递进。
    </div>
    <div class="card">
      <div class="sub" style="margin:0 0 8px">同样的 50 份请求，三种打法的得分（本游戏实算）：</div>
      <table class="cmp">
        <tr><th>策略</th><th>得分</th><th>说明</th></tr>
        <tr><td>全放行</td><td>${BASE.release.score}</td><td>${BASE.release.missed} 个攻击漏网</td></tr>
        <tr><td>盲从网关</td><td>${BASE.obey.score}</td><td>继承网关全部盲区</td></tr>
        <tr><td>自己判断</td><td>${BASE.perfect.score}</td><td>满分基准</td></tr>
      </table>
      <div class="tips">盲从网关比自己判断少 <b>${BASE.perfect.score-BASE.obey.score}</b> 分——这就是游戏。</div>
    </div>
    <button class="primary" onclick="startGame()">开始值班</button>
  </div>`);
  document.getElementById("root").innerHTML=""; document.getElementById("root").appendChild(r);
}

function startGame(){ state={i:0,score:0,caught:0,right:0,wrong:0,log:[]}; renderQ(); }

function renderQ(){
  const q=qs[state.i];
  const total=qs.length;
  const r=el(`<div class="card">
    <div class="bar">
      <span>${DAY_NAMES[q.day]||("第 "+q.day+" 天")}</span>
      <span>进度 <b>${state.i+1}/${total}</b> · 得分 <b id="sc">${state.score}</b></span>
    </div>
    <div class="req" id="req"></div>
    <div class="acts">
      <button class="act" onclick="choose('release')">放行<small>RELEASE · 直接通过</small></button>
      <button class="act" onclick="choose('redact')">脱敏<small>REDACT · 遮敏感字段</small></button>
      <button class="act" onclick="choose('block')">拦截<small>BLOCK · 直接拒绝</small></button>
    </div>
    <div class="feedback" id="fb"></div>
  </div>`);
  document.getElementById("root").innerHTML=""; document.getElementById("root").appendChild(r);
  document.getElementById("req").textContent=q.text;
}

function choose(act){
  const q=qs[state.i];
  const correct = (act===q.truth_action);
  let delta;
  if(correct){ delta = q.score_right + (q.engine_agrees?0:q.catch_bonus); state.right++; if(!q.engine_agrees) state.caught++; }
  else { delta = q.penalty_wrong; state.wrong++; }
  state.score += delta;
  state.log.push({id:q.id, act, correct, delta, engineAgrees:q.engine_agrees});

  const fb=document.getElementById("fb");
  const agree = (act===q.engine_action);
  let verdictTag = correct
    ? `<span class="tag t-right">判定正确</span>`
    : `<span class="tag t-wrong">判定错误</span>`;
  let catchTag = (correct && !q.engine_agrees)
    ? `<span class="tag t-catch">纠正网关误判 +${q.catch_bonus}</span>` : "";
  const engActZh = AZ[q.engine_action];
  const truthZh = AZ[q.truth_action];
  fb.innerHTML = `
    <div class="fb-row">${verdictTag} ${catchTag}
      <span class="delta ${delta>=0?'pos':'neg'}">${delta>=0?'+':''}${delta}</span></div>
    <div class="fb-row">你的判定：<b>${AZ[act]}</b> ·
      真相应为：<b style="color:var(--accent)">${truthZh}</b></div>
    <div class="fb-row eng">网关建议：<b>${engActZh}</b>（${q.engine_decision} · 风险 ${q.engine_risk} ·
      命中规则 ${q.engine_rules.join(", ")||"—"}）· 你${agree?"<span style='color:var(--good)'>同意</span>":"<span style='color:var(--warn)'>推翻</span>"}了网关</div>
    ${correct&&!q.engine_agrees?'<div class="tips">网关在这里是错的，你推翻了它——这正是得分点。</div>':''}
    ${!correct&&q.kind==='benign'?'<div class="tips" style="color:var(--bad)">这是正当请求，误杀扣 '+q.penalty_wrong+' 分，最贵的一类错误。</div>':''}
    <div style="margin-top:14px;text-align:right">
      <button class="primary" onclick="next()">${state.i+1>=qs.length?'查看战报':'下一份 →'}</button>
    </div>`;
  fb.style.display="block";
  document.getElementById("sc").textContent=state.score;
  // lock buttons
  document.querySelectorAll("button.act").forEach(b=>b.disabled=true);
}

function next(){
  if(state.i+1>=qs.length) return renderEnd();
  state.i++; renderQ();
}

function renderEnd(){
  const total=qs.length;
  const me=state.score;
  let tier, color;
  if(me>=BASE.perfect.score-20){tier="S · 网关克星";color="var(--good)";}
  else if(me>=BASE.obey.score+60){tier="A · 独立判断";color="var(--accent)";}
  else if(me>=BASE.obey.score){tier="B · 略胜于盲从";color="var(--warn)";}
  else {tier="C · 不如照抄机器";color="var(--bad)";}
  const r=el(`<div class="card center">
    <h1>值班战报</h1>
    <div class="verdict" style="color:${color}">${tier}</div>
    <div class="sub">你的得分 <b style="color:var(--accent);font-size:20px">${me}</b> ·
      正确 ${state.right} · 错误 ${state.wrong} · 纠正网关 ${state.caught}</div>
    <table class="cmp">
      <tr><th>策略</th><th>得分</th><th>你 vs 它</th></tr>
      <tr class="${me===BASE.release.score?'me':''}"><td>全放行</td><td>${BASE.release.score}</td><td>${me-BASE.release.score>=0?'+':''}${me-BASE.release.score}</td></tr>
      <tr class="${me===BASE.obey.score?'me':''}"><td>盲从网关</td><td>${BASE.obey.score}</td><td>${me-BASE.obey.score>=0?'+':''}${me-BASE.obey.score}</td></tr>
      <tr class="${me===BASE.perfect.score?'me':''}"><td>自己判断（满分基准）</td><td>${BASE.perfect.score}</td><td>${me-BASE.perfect.score>=0?'+':''}${me-BASE.perfect.score}</td></tr>
    </table>
    <div class="tips">你比盲从网关 ${me-BASE.obey.score>=0?'多':''}<b>${Math.abs(me-BASE.obey.score)}</b> 分${me-BASE.obey.score>=0?'——你守住了该守的':'——你比机器还糟，回去看看那 6 个它错的地方'}。</div>
    <div style="margin-top:18px">
      <button class="primary" onclick="startGame()">再来一班</button>
      <button class="ghost" onclick="renderStart()">回首页</button>
    </div>
  </div>`);
  document.getElementById("root").innerHTML=""; document.getElementById("root").appendChild(r);
}

renderStart();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
