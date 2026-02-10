
    function addDone(type,state=0,act="val"){

        var id = ""
        var step1 = editor1.getHtml();
        var step2 = editor2.getHtml();
        var step3 = editor3.getHtml();
        var step4 = editor4.getHtml();
        if (editor1.getText()=="" && editor2.getText()=="" && editor3.getText()=="" && editor4.getText()==""){
            alert("文档内容不能全为空")
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
                    alert("添加入库成功")
                }
                id = data.id
            }
        })
        return id;
    }

    function valDone(type, id) {
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
                if (data.code == -1) {
                    alert(data.msg)
                    location.reload()
                    return
                } else {
                    alert("评估完成")
                    location.href = "/user/aiVal/question?id=" + id+'&type='+type
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                if (textStatus === 'timeout') {
                    alert("网络超时，请检查网络")
                    location.reload()
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
          layer.open({
            type: 1
            ,title: false //不显示标题栏
            ,closeBtn: false
            ,area: ['300px', '175px']
            ,shade: 0.8
            ,id: 'LAY_layuipro' //设定一个id，防止重复弹出
            ,btn: ['继续添加', '返回列表页']
            ,btnAlign: 'c'
            ,moveType: 1 //拖拽模式，0或者1
            ,content: `
                        <div style='margin-top: 25px;text-align: center'>您的文档已入库，Ai大模型评估中，请稍后....</div>
                        <div style='margin-top: 0px;text-align: center'><img src="/static/img/ajax-loader.gif"></div>
                        <div style='margin-top: 0px;text-align: center'>你可以继续等待或者</div>
                       `
            ,success: function(layero){
                var btn = layero.find('.layui-layer-btn');
                btn.find('.layui-layer-btn0').attr({
                    href: '/user/aiVal/add?type='+type
                    ,target: '_self'
                });
                btn.find('.layui-layer-btn1').attr({
                    href: '/user/aiVal/list?type='+type
                    ,target: '_self'
                });
            }
        });
    }

    function editDone(id,state=0,act='val',type) {
        var step1 = editor1.getHtml();
        var step2 = editor2.getHtml();
        var step3 = editor3.getHtml();
        var step4 = editor4.getHtml();
        if (editor1.getText()=="" && editor2.getText()=="" && editor3.getText()=="" && editor4.getText()==""){
            alert("文档内容不能全为空")
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
                    alert("编辑入库成功")
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
    $('#delete_all').on('click', function(){
        var url = $(this).attr('url');
        var arr = []
        $('#tb input[type=checkbox]').each(function(){
            if(true == $(this).is(':checked')){
                arr.push($(this).val())
            }
        });
        if (arr.length == 0) {
            alert("至少选中一个")
            return
        }
        if(confirm("你确认要批量删除你选中的记录嘛？")){
            $.ajax({
                url: url,
                type: "POST",
                contentType: "application/json;charset=UTF-8",
                data: JSON.stringify({"ids":arr}),
                success: function (data) {
                    alert(data.msg);
                    location.reload();
                }
            })
        }
    })

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

