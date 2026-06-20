// ============================================================
// OLED 显示 UI — 头文件
// 使用 U8g2 驱动 128x64 OLED (SSD1306, I2C)
// ============================================================
#ifndef OLED_UI_H
#define OLED_UI_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "config.h"
#include "privacy_state_machine.h"

class OLED_UI {
public:
    OLED_UI();

    // 初始化 I2C + OLED
    bool begin();

    // 主渲染: 刷新全部显示内容
    void render(const PrivacyStateMachine& sm, const TargetInfo& info, bool pcConnected);

    // 显示启动画面
    void showSplash();

    // 显示错误信息
    void showError(const char* msg);

private:
    U8G2_SSD1306_128X64_NONAME_F_HW_I2C _u8g2;
    bool _ok = false;
    unsigned int _renderCount = 0;

    // 内部绘制函数
    void _drawHeader(const char* stateCN, const TargetInfo& info);
    void _drawTargetType(const TargetInfo& info, int y);
    void _drawFooter(bool pcConnected);
};

#endif // OLED_UI_H
