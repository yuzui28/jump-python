(function () {

importPackage(java.io);
importPackage(android.os);
importPackage(android.view);
importPackage(android.widget);
importPackage(android.graphics);
importPackage(android.graphics.drawable);
importPackage(android.content);

var PY_ROOT = String(shortx.getShortXDir()) + "/jump_python";
var PYTHON = "/data/data/com.termux/files/usr/bin/python";
var PY_SCRIPT = PY_ROOT + "/jump.py";
var PY_CONFIG = PY_ROOT + "/config.json";
var PY_IMG = PY_ROOT + "/shortx_jump.png";
var PY_RESULT = PY_ROOT + "/jump_result.json";
var PY_DEBUG = PY_ROOT + "/jump_debug.png";

var JumpPy_STATE = { wm:null, view:null, running:false, status:null, runBtn:null };

function log(msg){ console.log("[跳一跳-Python] " + msg); }

function readStream(stream){
    var br=new BufferedReader(new InputStreamReader(stream));
    var sb="", line;
    while((line=br.readLine())!=null) sb+=line+"\n";
    br.close(); return sb;
}

function shell(cmd){
    try{
        log("执行: " + cmd);
        var p=java.lang.Runtime.getRuntime().exec(["su","-c",cmd]);
        var code=p.waitFor();
        var out=readStream(p.getInputStream());
        var err=readStream(p.getErrorStream());
        if(out) log("stdout: " + out);
        if(err) log("stderr: " + err);
        if(code!==0) log("exitCode: " + code);
        return code===0;
    }catch(e){ log("shell失败: "+e); return false; }
}

function exists(path){ return new File(path).exists(); }

function readFile(path){
    var br=new BufferedReader(new InputStreamReader(new FileInputStream(path)));
    var sb="", line;
    while((line=br.readLine())!=null) sb+=line+"\n";
    br.close(); return sb;
}

function writeFile(path,text){
    var fw=new FileWriter(path,false);
    fw.write(text); fw.flush(); fw.close();
}

function ensureFiles(){
    shell("mkdir -p '" + PY_ROOT + "' && chmod 777 '" + PY_ROOT + "'");
    if(!exists(PY_SCRIPT)){
        writeFile(PY_SCRIPT, "请把 jump.py 放到这里: " + PY_SCRIPT + "\n");
        shell("chmod 777 '" + PY_SCRIPT + "'");
        throw "首次运行已创建目录，请把 jump.py 放入 " + PY_ROOT;
    }
    if(!exists(PY_CONFIG)){
        var cfg={
            area_left:80, area_top:800, area_right:1360, area_bottom:2200,
            offset_x:0, offset_y:120, press_x:540, press_y:1600,
            min_press:200, max_press:2200, scan_step:3,
            piece_min_pixels:80, target_min_count:5,
            target_min_width:30, target_max_width:560,
            draw_debug:true, wait_after_jump:1200
        };
        writeFile(PY_CONFIG, JSON.stringify(cfg));
        shell("chmod 666 '" + PY_CONFIG + "'");
    }
}

function uiRun(fn){ new Handler(Looper.getMainLooper()).post(new java.lang.Runnable({run:fn})); }

function updateStatus(text){
    uiRun(function(){
        if(JumpPy_STATE.status!=null) JumpPy_STATE.status.setText(text || (JumpPy_STATE.running ? "运行中" : "已暂停"));
        if(JumpPy_STATE.runBtn!=null) JumpPy_STATE.runBtn.setText(JumpPy_STATE.running ? "暂停" : "启动");
    });
}

function runPythonOnce(needJump){
    ensureFiles();

    if(!shell("screencap -p '" + PY_IMG + "' && chmod 666 '" + PY_IMG + "'")) throw "截图失败";

    var cmd = "'" + PYTHON + "' '" + PY_SCRIPT + "' " +
        "--input '" + PY_IMG + "' " +
        "--config '" + PY_CONFIG + "' " +
        "--output '" + PY_RESULT + "' " +
        "--debug '" + PY_DEBUG + "'";

    shell(cmd);

    if(!exists(PY_RESULT)) throw "结果文件不存在: " + PY_RESULT;

    var obj=JSON.parse(readFile(PY_RESULT));
    if(!obj.ok) throw "识别失败: " + obj.error;

    var info = "Python识别成功\n" +
        "棋子: " + obj.piece_x + "," + obj.piece_y + "\n" +
        "目标: " + obj.target_x + "," + obj.target_y + "\n" +
        "距离: " + obj.distance + "\n" +
        "按压: " + obj.press_ms + "ms\n" +
        "耗时: " + obj.elapsed_ms + "ms";
    log(info); updateStatus(info);

    if(needJump){
        shell("input swipe " + obj.press_x + " " + obj.press_y + " " +
            obj.press_x + " " + obj.press_y + " " + obj.press_ms);
    }
    return obj;
}

function startLoop(){
    if(JumpPy_STATE.running) return;
    JumpPy_STATE.running=true; updateStatus("运行中");
    new java.lang.Thread(new java.lang.Runnable({run:function(){
        while(JumpPy_STATE.running){
            try{
                runPythonOnce(true);
                var wait=1200;
                try{
                    var cfg=JSON.parse(readFile(PY_CONFIG));
                    if(cfg.wait_after_jump) wait=parseInt(cfg.wait_after_jump);
                }catch(e){}
                var t=0;
                while(JumpPy_STATE.running && t<wait){
                    java.lang.Thread.sleep(100); t+=100;
                }
            }catch(e){
                log("停止: "+e);
                JumpPy_STATE.running=false;
                updateStatus("停止: "+e);
                break;
            }
        }
    }})).start();
}

function stopLoop(){ JumpPy_STATE.running=false; updateStatus("已暂停"); }
function toggleLoop(){ if(JumpPy_STATE.running) stopLoop(); else startLoop(); }

function makeBtn(ctx,text){
    var v=new TextView(ctx);
    v.setText(text); v.setTextSize(14); v.setTextColor(0xff302c27);
    v.setGravity(Gravity.CENTER); v.setPadding(18,13,18,13);
    var bg=new GradientDrawable(); bg.setColor(0xffe2d9cb); bg.setCornerRadius(20);
    v.setBackgroundDrawable(bg); return v;
}

function addRow(ctx,root,arr){
    var row=new LinearLayout(ctx); row.setOrientation(LinearLayout.HORIZONTAL); row.setPadding(0,5,0,5);
    for(var i=0;i<arr.length;i++) row.addView(arr[i]);
    root.addView(row);
}

function removeFloat(){
    JumpPy_STATE.running=false;
    try{ if(JumpPy_STATE.wm!=null && JumpPy_STATE.view!=null) JumpPy_STATE.wm.removeView(JumpPy_STATE.view); }catch(e){}
    JumpPy_STATE.view=null;
}

function params(x,y){
    var type=Build.VERSION.SDK_INT>=26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE;
    var p=new WindowManager.LayoutParams(WindowManager.LayoutParams.WRAP_CONTENT,WindowManager.LayoutParams.WRAP_CONTENT,type,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT);
    p.gravity=Gravity.LEFT|Gravity.TOP; p.x=x; p.y=y; return p;
}

function attachDrag(root,p){
    var dx=0,dy=0,sx=0,sy=0;
    root.setOnTouchListener(new View.OnTouchListener({onTouch:function(v,e){
        if(e.getAction()===MotionEvent.ACTION_DOWN){ dx=e.getRawX(); dy=e.getRawY(); sx=p.x; sy=p.y; return false; }
        if(e.getAction()===MotionEvent.ACTION_MOVE){
            p.x=parseInt(sx+e.getRawX()-dx); p.y=parseInt(sy+e.getRawY()-dy);
            try{ JumpPy_STATE.wm.updateViewLayout(root,p); }catch(ex){}
            return false;
        }
        return false;
    }}));
}

function createFloat(){
    try{ ensureFiles(); }catch(e){ log(String(e)); }

    var ctx=android.app.ActivityThread.currentApplication();
    if(ctx==null){ log("Context为空"); return; }
    JumpPy_STATE.wm=ctx.getSystemService(Context.WINDOW_SERVICE);

    var root=new LinearLayout(ctx); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(16,16,16,16);
    var bg=new GradientDrawable(); bg.setColor(0xfff7f2e8); bg.setCornerRadius(32); root.setBackgroundDrawable(bg);

    var title=new TextView(ctx); title.setText("跳一跳 Python版"); title.setTextSize(16); title.setTextColor(0xff302c27); title.setGravity(Gravity.CENTER); root.addView(title);

    JumpPy_STATE.status=new TextView(ctx);
    JumpPy_STATE.status.setText("目录: " + PY_ROOT);
    JumpPy_STATE.status.setTextSize(12); JumpPy_STATE.status.setTextColor(0xff675c52);
    JumpPy_STATE.status.setGravity(Gravity.CENTER); JumpPy_STATE.status.setPadding(6,8,6,8); root.addView(JumpPy_STATE.status);

    var run=makeBtn(ctx,"启动"), preview=makeBtn(ctx,"预览"), stop=makeBtn(ctx,"暂停"), exit=makeBtn(ctx,"退出");
    JumpPy_STATE.runBtn=run; addRow(ctx,root,[run,preview,stop,exit]);

    run.setOnClickListener(new View.OnClickListener({onClick:function(){ toggleLoop(); }}));
    stop.setOnClickListener(new View.OnClickListener({onClick:function(){ stopLoop(); }}));
    exit.setOnClickListener(new View.OnClickListener({onClick:function(){ removeFloat(); }}));
    preview.setOnClickListener(new View.OnClickListener({onClick:function(){
        new java.lang.Thread(new java.lang.Runnable({run:function(){
            try{ runPythonOnce(false); }catch(e){ log("预览失败: "+e); updateStatus("预览失败: "+e); }
        }})).start();
    }}));

    var p=params(80,300); attachDrag(root,p);
    JumpPy_STATE.view=root; JumpPy_STATE.wm.addView(root,p);
}

try{ createFloat(); }catch(e){ log("启动失败: "+e); }

})();
