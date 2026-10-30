// 键盘/摇杆取样：方向、最后按下优先、连按两下冲刺、按键排队。不开浏览器。
'use strict';
const assert = require('node:assert/strict');
let now = 0;
const Input = require('../input.js');
const input = new Input(() => now);
assert.deepEqual(input.sample(), { h: 0, v: 0, press: [] });
input.hold('KeyD', 'right');
assert.deepEqual(input.sample(), { h: 1, v: 0, press: [] });
input.hold('KeyA', 'left');                      // 后按的方向优先
assert.equal(input.sample().h, -1);
input.release('KeyA');
assert.equal(input.sample().h, 1);
input.hold('KeyS', 'down');
assert.deepEqual(input.sample(), { h: 1, v: -1, press: [] });
input.clear();
// 连按两下：260 毫秒内同方向 = dash
now = 1000; input.hold('KeyD', 'right'); input.release('KeyD');
now = 1200; input.hold('KeyD', 'right');
assert.deepEqual(input.sample().press, ['dash+']);
input.release('KeyD');
now = 1300; input.hold('KeyD', 'right');          // 第三下不再连成冲刺
assert.deepEqual(input.sample().press, []);
input.release('KeyD');
now = 2000; input.hold('KeyA', 'left'); input.release('KeyA');
now = 2500; input.hold('KeyA', 'left');           // 太慢不算
assert.deepEqual(input.sample().press, []);
input.clear();
// 攻击键排队，取一次就清空，最多 8 个
input.press('p'); input.press('z');
assert.deepEqual(input.sample().press, ['p', 'z']);
assert.deepEqual(input.sample().press, []);
for (let i = 0; i < 20; i++) input.press('k');
assert.equal(input.sample().press.length, 8);
// 摇杆：与键盘合并，键盘优先；拉向一侧两下也冲刺
now = 5000; input.setPad(-1, 0); input.setPad(0, 0);
now = 5100; input.setPad(-1, -1);
assert.deepEqual(input.sample(), { h: -1, v: -1, press: ['dash-'] });
input.hold('ArrowUp', 'up');
assert.deepEqual(input.sample(), { h: -1, v: 1, press: [] });
assert.equal(Input.BUTTON.Space, 'z');
assert.equal(Input.BUTTON.KeyP, 'x');
console.log('input: directions, priority, double-tap dash, press queue and pad passed');
