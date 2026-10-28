'use strict';
const assert = require('node:assert/strict');
const Input = require('../input.js');
const input = new Input();
assert.equal(input.sample(), 'stay');
input.press('W', 'up');
assert.equal(input.sample(), 'up');
assert.equal(input.sample(), 'up', 'held direction repeats each round');
input.press('D', 'right');
input.press('W', 'up');
assert.equal(input.sample(), 'right', 'OS key repeat cannot steal priority');
input.release('D');
assert.equal(input.sample(), 'up');
input.press('tap', 'bomb'); input.release('tap');
assert.equal(input.sample(), 'bomb', 'quick taps survive until the next round');
assert.equal(input.sample(), 'up', 'placing consumes a whole round');
input.press('touch-bomb', 'bomb');
assert.equal(input.sample(), 'bomb');
assert.equal(input.sample(), 'bomb');
input.clear();
assert.equal(input.sample(), 'stay', 'blur/pause clears stuck keys and pending bombs');
{
  // 点一下就松开的方向在下一次取样时仍然算一步，只算一次
  const tap = new Input();
  tap.press('k', 'left'); tap.release('k');
  assert.equal(tap.sample(), 'left');
  assert.equal(tap.sample(), 'stay');
  // 放弹优先，点过的方向留到下一回合
  tap.press('a', 'right'); tap.release('a'); tap.press('b', 'bomb'); tap.release('b');
  assert.equal(tap.sample(), 'bomb');
  assert.equal(tap.sample(), 'right');
}
console.log('Input: held keys, latest direction, taps, repeat and clear passed');
