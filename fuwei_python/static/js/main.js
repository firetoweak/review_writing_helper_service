$(document).ready(function() {
    // 卡片悬停效果增强
    $('.product-card').hover(
        function() {
            $(this).css('transform', 'translateY(-10px)');
        },
        function() {
            $(this).css('transform', 'translateY(0)');
        }
    );

    // 平滑滚动效果
    $('a[href^="#"]').on('click', function(event) {
        var target = $(this.getAttribute('href'));
        if (target.length) {
            event.preventDefault();
            $('html, body').stop().animate({
                scrollTop: target.offset().top - 80
            }, 800);
        }
    });

    // 导航栏滚动效果
    $(window).scroll(function() {
        if ($(this).scrollTop() > 50) {
            $('.header').addClass('header-scrolled');
        } else {
            $('.header').removeClass('header-scrolled');
        }
    });

    // 添加导航栏当前项高亮
    $('.nav-link').on('click', function() {
        $('.nav-link').removeClass('active');
        $(this).addClass('active');
    });

    // 登录弹框功能
    // 点击登录/注册按钮显示弹框
    $('.btn-login').on('click', function(e) {
        e.preventDefault();
        $('#loginModal, #modalOverlay').fadeIn(300);
        $('body').css('overflow', 'hidden'); // 防止背景滚动
    });
    
    // 点击关闭按钮或背景遮罩关闭弹框
    $('#closeLoginModal, #modalOverlay').on('click', function() {
        $('#loginModal, #modalOverlay').fadeOut(300);
        $('body').css('overflow', '');
    });
    
    // 阻止点击弹框内容时关闭弹框
    $('.login-container').on('click', function(e) {
        e.stopPropagation();
    });
    
    // 登录/注册标签切换
    $('.tab-btn').on('click', function() {
        const tab = $(this).data('tab');
        
        // 切换标签按钮样式
        $('.tab-btn').removeClass('active');
        $(this).addClass('active');
        
        // 切换表单内容
        $('.tab-content').hide();
        $(`#${tab}Tab`).fadeIn(300);
    });
    
    // 密码显示/隐藏切换
    $('.toggle-password').on('click', function() {
        const passwordInput = $(this).closest('.password-input').find('input');
        if (passwordInput.attr('type') === 'password') {
            passwordInput.attr('type', 'text');
            $(this).html('<img src="/static/images/register/eye-closed-icon.svg" alt="显示密码">')
        } else {
            passwordInput.attr('type', 'password');
            $(this).html('<img src="/static/images/register/eye-icon.svg" alt="显示密码">')

        }
    });
    
    // 登录表单提交
    $('#loginForm').on('submit', function(e) {
        e.preventDefault();
        
        const loginInput = $('#loginInput').val();
        const password = $('#loginPassword').val();
        
        // 简单验证
        if (!loginInput) {
            alert('请输入手机号/邮箱');
            return;
        }
        
        if (!password) {
            alert('请输入密码');
            return;
        }
        
        // 这里应该添加登录的AJAX请求
        console.log('登录信息:', { loginInput, password });
        
        // 登录成功后关闭弹框
        // $('#loginModal, #modalOverlay').fadeOut(300);
        // $('body').css('overflow', '');
    });
    
    // 立即注册点击事件

    
    // 忘记密码点击事件
    $('.forgot-password').on('click', function() {
        // 关闭登录弹框
        $('#loginModal').fadeOut(300);
        
        // 显示忘记密码弹框
        $('#forgotModal').fadeIn(300);
    });
    
    // 点击关闭按钮或背景遮罩关闭忘记密码弹框
    $('#closeForgotModal, #modalOverlay').on('click', function() {
        $('#forgotModal, #modalOverlay').fadeOut(300);
        $('body').css('overflow', '');
    });
    
    // 阻止点击忘记密码弹框内容时关闭弹框
    $('.forgot-container').on('click', function(e) {
        e.stopPropagation();
    });
    
    // 忘记密码表单提交
    $('#forgotForm').on('submit', function(e) {
        e.preventDefault();
        
        const contactInfo = $('#contactInfo').val();
        
        // 简单验证
        if (!contactInfo) {
            alert('请输入联系方式');
            return;
        }
        
        // 这里应该添加发送重置密码请求的AJAX请求
        console.log('发送重置密码请求:', { contactInfo });
        
        // 提交成功后显示提示信息
        alert('密码重置链接已发送到您的联系方式，请查收');
        
        // 关闭忘记密码弹框
        $('#forgotModal, #modalOverlay').fadeOut(300);
        $('body').css('overflow', '');
    });

    // 阻止点击模态框内容时关闭模态框
    // 阻止点击profile模态框内容时关闭模态框
    $('#profileModal').on('click', function(e) {
        e.stopPropagation();
    });
    
    // 确保点击关闭按钮时关闭模态框
    $('#profileModal .btn-close').on('click', function() {
        $('#profileModal, #modalOverlay').fadeOut(300);
        $('body').css('overflow', '');
    });
}); 


$('.register-link').on('click', function(e) {
    e.preventDefault();
    $('#registerModal, #modalOverlay').fadeIn(300);
    $('body').css('overflow', 'hidden'); // 防止背景滚动
});

// 点击关闭按钮或背景遮罩关闭弹框
$('#closeRegisterModal, #modalOverlay').on('click', function() {
    $('#registerModal, #modalOverlay').fadeOut(300);
    $('body').css('overflow', '');
});

// 注册表单提交（第一步）
$('#registerForm').on('submit', function(e) {
    e.preventDefault();
    
    const phoneNumber = $('#phoneNumber').val();
    const smsCode = $('#smsCode').val();
    const captcha = $('#captcha').val();
    const password = $('#password').val();
    const confirmPassword = $('#confirmPassword').val();
    
    // 简单验证
    if (!phoneNumber) {
        alert('请输入手机号码');
        return;
    }
    
    if (!smsCode) {
        alert('请输入短信验证码');
        return;
    }
    
    if (!captcha) {
        alert('请输入验证码');
        return;
    }
    
    if (!password) {
        alert('请输入密码');
        return;
    }
    
    if (password !== confirmPassword) {
        alert('两次输入的密码不一致');
        return;
    }
    
});

// 点击关闭按钮或背景遮罩关闭第二步弹框
$('#closeRegisterStep2Modal, #modalOverlay').on('click', function() {
    $('#registerStep2Modal, #modalOverlay').fadeOut(300);
    $('body').css('overflow', '');
});

// 阻止点击第二步弹框内容时关闭弹框
$('.register-container').on('click', function(e) {
    e.stopPropagation();
});

// 注册表单提交（第二步）
$('#registerStep2Form').on('submit', function(e) {
    e.preventDefault();
    
    const userFullName = $('#userFullName').val();
    const userEmail = $('#userEmail').val();
    const companyName = $('#companyName').val();
    const jobTitle = $('#jobTitle').val();
    
    // 简单验证
    if (!userFullName) {
        alert('请输入姓名');
        return;
    }
    
    if (!userEmail) {
        alert('请输入邮箱');
        return;
    }
    
    if (!companyName) {
        alert('请输入公司名称');
        return;
    }
    
    if (!jobTitle) {
        alert('请输入职位');
        return;
    }


    
    // 注册成功后关闭弹框
    $('#registerStep2Modal, #modalOverlay').fadeOut(300);
    $('body').css('overflow', '');
    
    // 显示注册成功提示
    alert('注册成功！');
});

// 联系我们和个人资料点击事件
$('#contactUsLink, #contactUsFooterLink, #profileLink,#aboutUsLink').on('click', function(e) {
    e.preventDefault();
    
    // 获取点击元素的位置信息
    const clickedElement = $(this);
    const elementPosition = clickedElement.offset();
    const elementWidth = clickedElement.outerWidth();
    const elementHeight = clickedElement.outerHeight();
    let modalId = "";
    
    if(this.id === 'profileLink') {
        $(this).find('img').attr('src', '/static/images/index/up.svg');
        $(this).css('color', '#217EFD');
        // 显示个人资料弹框
        modalId = '#profileModal';
        const Modal = $(modalId);
        Modal.css({
            'top': elementPosition.top + elementHeight + 10,
            'right': '10%'
        });
        Modal.fadeIn(300);
        $('#modalOverlay').fadeIn(300);
    } else if(this.id === 'contactUsLink' || this.id === 'contactUsFooterLink') {
        // 显示联系我们弹框
        $('#contactModal, #modalOverlay').fadeIn(300);
        $('body').css('overflow', 'hidden'); // 防止背景滚动
    } else if(this.id === 'aboutUsLink') {
        // 显示关于我们弹框
        $('#aboutUsModal, #modalOverlay').fadeIn(300);
        $('body').css('overflow', 'hidden'); // 防止背景滚动
    }
});

// 点击关闭按钮或背景遮罩关闭联系我们弹框和关于我们弹框
$('#closeContactModal, #closeAboutUsModal, #modalOverlay').on('click', function() {
    $('#contactModal, #aboutUsModal, #modalOverlay').fadeOut(300);
    $('body').css('overflow', '');
});

// 点击关闭按钮或背景遮罩关闭profile模态框
$('.btn-close, #modalOverlay').on('click', function() {
    $('#profileModal, #modalOverlay').fadeOut(300);
    $('body').css('overflow', '');
    $('#profileLink').find('img').attr('src', '/static/images/index/down.svg');
    $('#profileLink').css('color', '#000205');
});

// 阻止点击联系我们弹框内容时关闭弹框
$('.contact-container').on('click', function(e) {
    e.stopPropagation();
});

$('.card-body').hover(

    function() {
        if($(this).find('.card-start-button').length>0) {
            $(this).find('.card-features').hide();
            $(this).find('.card-start-button').show();
        }
    },
    function() {
        if($(this).find('.card-start-button').length>0) {
            $(this).find('.card-features').show();
            $(this).find('.card-start-button').hide();
        }
    }
  );
$('#allCheckbox').on('change', function() {
    var $checkboxes = $('input[type="checkbox"][name="item"]:not(:disabled)');
    $checkboxes.prop('checked', this.checked);
});

function isDesktopDevice() {
    const userAgent = navigator.userAgent.toLowerCase();
    const platform = navigator.platform.toLowerCase();
 
    // 排除移动设备（手机、平板）
    const isMobile = /android|iphone|ipad|ipod|blackberry|iemobile|opera mini|windows phone/i.test(userAgent);
    if (isMobile) {
        return false;
    }
    // 检查是否为桌面系统（Windows/macOS/Linux）
    const isDesktop = /win|mac|linux/i.test(platform);
    return isDesktop;
}
if(!isDesktopDevice()){
    $('#pcConfirm').show();
    $('#modalOverlayMobile').show()
}
$('#modalOverlayMobile,#pcConfirmButton').on('click', function() {
    $('#pcConfirm, #modalOverlayMobile').fadeOut(300);
    $('body').css('overflow', '');
});

// 从当前URL获取查询参数(公共方法)
function getUrlParams() {
    const urlParams = new URLSearchParams(window.location.search);
    const params = {};
    for (let [key, value] of urlParams) {
        params[key] = value;
    }
    return params;
}