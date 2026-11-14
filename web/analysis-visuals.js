/* Pure geometry/score helpers are also tested under Node. */
(function(root){
  function center(square,orientation='white'){
    if(!/^[a-h][1-8]$/.test(square))throw new Error('invalid square');
    const file=square.charCodeAt(0)-97,rank=Number(square[1])-1;
    return orientation==='white'?[file*100+50,(7-rank)*100+50]:[(7-file)*100+50,rank*100+50];
  }
  function style(score,best,side){
    const loss=Math.max(0,(best-score)*(side==='white'?1:-1));
    const mate=Math.abs(score)>=99000||Math.abs(best)>=99000;
    if(mate)return loss===0?{color:'#6fe1ba',width:18,label:'최선 메이트 평가'}:{color:'#dd91ed',width:9,label:'메이트 수순 차이'};
    return loss<=30?{color:'#6fe1ba',width:18,label:'최선 대비 0.30폰 이내'}:
      loss<=100?{color:'#f3cb75',width:13,label:'최선 대비 1폰 이내'}:{color:'#ed9393',width:8,label:'최선 대비 1폰 초과'};
  }
  function arrows(lines,side,orientation,legal){
    if(!lines?.length)return [];
    return lines.slice(0,3).filter(l=>l.pv?.[0]&&legal.includes(l.pv[0])).map((l,i)=>({
      from:center(l.pv[0].slice(0,2),orientation),to:center(l.pv[0].slice(2,4),orientation),
      rank:i+1,move:l.pv[0],...style(l.score,lines[0].score,side)
    }));
  }
  root.TalVisuals={center,style,arrows};
  if(typeof module!=='undefined')module.exports=root.TalVisuals;
})(globalThis);
