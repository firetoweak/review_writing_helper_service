



$('#header-sendCode').click(function () {
    $.ajax({
        type: "POST",
        url: "/user/send_change_mobile_code",
        contentType: "application/json;charset=UTF-8",
        data: JSON.stringify({
            mobile: $('#header-mobile').val(),
        }),
        async:true,
        success: function (data) {
            if(data.code==1) {
                showToast('success', data.msg);
                $('#header-sendCodeP').html(`<span style="color: grey;font-size: 13px">已发送剩余<span  style="color: red" id="sec">300s</span>失效</span>`)
                headerExecSecond(300)
            }else {
                showToast('warning', data.msg);
            }
        }
    })
})
$('#changeMobileDone').click(function () {
    $.ajax({
        type: "POST",
        url: "/user/change_mobile",
        contentType: "application/json;charset=UTF-8",
        data: JSON.stringify({
            mobile: $('#header-mobile').val(),
            mobileCode: $('#header-mobileCode').val()
        }),
        async:false,
        success: function (data) {
            if (data.code == 1) {
                showToast('success', data.msg);
                $('#changeMobileModel').fadeOut(300);
                setTimeout(() => location.href='/', 2000)
            }else {
                showToast('warning', data.msg);
            }
        }
    })
})


function headerExecSecond(x){
    x = x - 1
    var s = x.toString();
    $('#sec').html(s+"s")
    if(x>0) {
        setTimeout(() => headerExecSecond(x), 1000)
    }else{
        $('#header-sendCodeP').html(`<a style="cursor: pointer;font-size: 11px" id="header-sendCode" >发送短信验证码</a>`)
    }
}

// 点击关闭按钮关闭抽屉
$('#closeDrawer, .drawer-overlay').click(function() {
    $('.drawer-container').animate({right: '-500px'}, 300, function() {
        $('#addColleagueDrawer').fadeOut(300);
    });
});
// 防止点击抽屉内容时关闭抽屉
$('.drawer-container').click(function(e) {
    e.stopPropagation();
});


function addDone(type,state=0,act="val"){

    var id = ""
    var step1 = editor1.getHtml();
    var step2 = editor2.getHtml();
    var step3 = editor3.getHtml();
    var step4 = editor4.getHtml();
    if (editor1.getText()=="" && editor2.getText()=="" && editor3.getText()=="" && editor4.getText()==""){
        showToast("warning", "文档内容不能全为空");
        return 0
    }
    $.ajax({
        type: "POST",
        url: "/user/aiVal/add?type=" + type,
        contentType: "application/json;charset=UTF-8",
        data: JSON.stringify({
            step1: step1,
            step2: step2,
            step3: step3,
            step4: step4,
            state: state,
        }),
        async: false,
        success: function (data) {
            if(act=="add") {
                 showToast("success", "暂存成功");
                 location.href='/user/aiVal/edit?id='+data.id+'&type='+type
            }
            id = data.id
        }
    })
    return id;
}

function valDone(type, id) {
    var valDoneModal = new bootstrap.Modal(document.getElementById('valDoneModal'));
    $('#timeComfirmWinContinueAdd').click(function (){
        location.href = '/user/aiVal/add?type='+type
    })
    valDoneModal.show();
    $.ajax({
        type: "POST",
        url: "/user/aiVal/done?type=" + type,
        contentType: "application/json;charset=UTF-8",
        timeout: 400000,
        data: JSON.stringify({
            id: id,
        }),
        async: true,
        success: function (data) {
            console.log(data)
            if (data.code == -1) {
                alert(data.msg)
                location.reload()
                return ""
            }else if(data.code == -2){
                setTimeout(function() {
                    $('#NoMoney').modal('show')
                    $('#valDoneModal').modal('hide');
                }, 2000);
            }
            else {
                showToast("success", "完成评估",5000);
                setTimeout(function() {
                    location.href = "/user/aiVal/list?type="+type
                }, 3000);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            if (textStatus === 'timeout') {
                showToast("warning", "网络超时，请检查网络",5000);
                setTimeout(function() {
                    location.reload()
                }, 5000);
            } else {
                //alert("系统错误，系统暂时未能评估")
                setTimeout(function() {
                    console.log(textStatus)
                    console.log(errorThrown)
                    location.reload()
                }, 3000);
            }
        }
    })
}

function editDone(id,state=0,act='val',type) {
    var step1 = editor1.getHtml();
    var step2 = editor2.getHtml();
    var step3 = editor3.getHtml();
    var step4 = editor4.getHtml();
    if (editor1.getText()=="" && editor2.getText()=="" && editor3.getText()=="" && editor4.getText()==""){
        showToast("warning", "文档内容不能全为空");
        return 0
    }
    $.ajax({
        type: "POST",
        url: "/user/aiVal/edit?type="+type,
        contentType: "application/json;charset=UTF-8",
        data: JSON.stringify({
            id: id,
            step1: step1,
            step2: step2,
            step3: step3,
            step4: step4,
            state: state,
        }),
        async: false,
        success: function (data) {
            if(act=='edit') {
                showToast("success", "编辑入库成功");
                location.href='/user/aiVal/edit?id='+id+'&type='+type
            }
        }
    })
}

function askAi(question, id,type) {
    $('#aq').show()
    $('#aiQuestion').val("")
    $("#aq").scrollTop(0);
    var tmp_html = `
                       <div id ="tmp_div" style="margin-top: 16px">
                           <b>提问：${question}</b><br>
                           <span style="color: blue;">Ai正在思考您的问题，请稍后。。。。。<a onclick="location.reload()" style="cursor: pointer; text-decoration: underline;color: red">刷新</a></span>
                        </div>
                `
    $("#aq").prepend(tmp_html)
    $('#send').prop("disabled", true);
    $.ajax({
        type: "POST",
        url: "/user/aiVal/question?id=" + id+'&type='+type,
        contentType: "application/json;charset=UTF-8",
        data: JSON.stringify({
            question: question,
        }),
        async: true,
        timeout: 400000,
        success: function (data) {
            if(data.code==1){
                let result = data.answer.replace(/\n/g, '<br>');
                var html = `
                    <div style="margin-top: 6px">
                        <b>问题：${question}</b><br>
                        Ai回答： <span style="color:blue">${result}</span>
                    </div>
                    `
                $('#tmp_div').remove()
                $("#aq").prepend(html)
                $("#send").prop("disabled", false);
            }else{
                alert(data.msg)
                $('#tmp_div').remove()
                $("#send").prop("disabled", false);
                if($('#aq div').length==0){
                    $('#aq').hide()
                }
                // if($('#aq div').==""){
                //     $('#aq').hide()
                // }
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            if (textStatus === 'timeout') {
                var tmp_html = `
                           <div id ="tmp_div" style="margin-top: 6px">
                               提问：${question}<br>
                               <span style="color: red">网络超时，请检查网络</span>
                           </div>
                            `
            } else {
                var tmp_html = `
                            <div id ="tmp_div" style="margin-top: 6px">
                                提问：${question}<br>
                                <span style="color: red">系统错误，系统暂时未能回答</span>
                            </div>
                        `
            }
            $('#tmp_div').html(tmp_html)
            $("#send").prop("disabled", false);
        }
    })
}

$('.icheck-me').on('ifChecked', function(event){
    $('#tb input[type=checkbox]').iCheck('check');
});
$('.icheck-me').on('ifUnchecked', function(event){
    $('#tb input[type=checkbox]').iCheck('uncheck');
});
$("#valAg").on("click",function(){
    var step1 = editor1.getHtml();
    var step2 = editor2.getHtml();
    var step3 = editor3.getHtml();
    var step4 = editor4.getHtml();
    if (editor1.getText()=="" && editor2.getText()=="" && editor3.getText()=="" && editor4.getText()==""){
        alert("文档内容不能全为空")
        return
    }
    var id = addDone(type,-2)
    valDone(type,id)
})

function setCircleProgress(percent) {
    var circle = document.querySelector('.circle-bar');
    var radius = circle.r.baseVal.value;
    var circumference = 2 * Math.PI * radius;
    var offset = circumference * (1 - percent / 100);
    circle.style.strokeDasharray = circumference;
    circle.style.strokeDashoffset = offset;
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// 更新计时器显示
function updateDisplay(timeLeft) {
    $('#timer').html(formatTime(timeLeft));
}

function startTimer(timeLeft,timerWait,isRunning,mess='') {
    if(mess!=''){
        $('#divAboutTime').html(mess)
    }
    if (!isRunning) {
        isRunning = true;
        timerWait = setInterval(() => {
            timeLeft++;
            updateDisplay(timeLeft);
            if (timeLeft <= 0) {
                clearInterval(timerWait);
                isRunning = false;
            }
        }, 1000);
    }
}