import struct
import unittest
from unittest.mock import Mock, patch
import numpy as np

from android_device import AndroidDevice


class AndroidDeviceTests(unittest.TestCase):
    def device(self):
        device = AndroidDevice('adb', 'test-device')
        device.capture = Mock(return_value=(1920, 1080))
        device.command = Mock(return_value=b'')
        return device

    def test_plan_uses_device_coordinates(self):
        device = self.device()
        device.execute([
            {'op': 'click', 'point': [.5, .8]},
            {'op': 'drag', 'from': [.4, .9], 'to': [.5, .55]},
        ])
        self.assertEqual(device.command.call_args_list[0].args,
                         ('shell', 'input', 'touchscreen', 'tap', 960, 864))
        self.assertEqual(device.command.call_args_list[1].args,
                         ('shell', 'input', 'touchscreen', 'swipe', 768, 972, 960, 594, 450))

    def test_invalid_later_target_prevents_entire_plan(self):
        device = self.device()
        with self.assertRaises(ValueError):
            device.execute([{'op': 'click', 'point': [.5, .5]},
                            {'op': 'click', 'point': [float('nan'), .5]}])
        device.command.assert_not_called()

    def test_rotation_stops_before_input(self):
        device = self.device()
        device.capture.side_effect = [(1920, 1080), (1080, 1920)]
        with self.assertRaises(ValueError):
            device.execute([{'op': 'click', 'point': [.5, .5]}])
        device.command.assert_not_called()

    def test_capture_uses_rotated_frame_size(self):
        device = AndroidDevice('adb', 'test-device')
        device.command = Mock(return_value=b'\x89PNG\r\n\x1a\n' + b'\0'*8 + struct.pack('>II', 1920, 1080))
        self.assertEqual(device.capture(), (1920, 1080))

    def test_raw_frame_accepts_android_headers_and_rejects_truncation(self):
        device=AndroidDevice('adb','test')
        for header in (struct.pack('<III',2,3,1),struct.pack('<IIII',2,3,1,1)):
            device.command=Mock(return_value=header+bytes(range(24)))
            frame=device.frame()
            self.assertEqual(frame.shape,(3,2,3))
            np.testing.assert_array_equal(frame[0,0],[0,1,2])
        device.command=Mock(return_value=struct.pack('<IIII',2,3,1,1)+b'\0')
        with self.assertRaises(ValueError):device.frame()

    def test_raw_frame_timeout_uses_bounded_png_capture(self):
        import cv2
        import subprocess
        device=self.device()
        pixels=np.full((3,2,3),(10,20,30),dtype=np.uint8)
        _,png=cv2.imencode('.png',pixels)
        device.command.side_effect=[subprocess.TimeoutExpired('screencap',3),png.tobytes()]
        np.testing.assert_array_equal(device.frame()[0,0],[30,20,10])
        self.assertEqual(device.command.call_args.args,('exec-out','screencap','-p'))
        self.assertEqual(device.command.call_args.kwargs,{'timeout':3})

    def test_stability_check_honors_stop_before_capture(self):
        device=self.device()
        device.frame=Mock()
        def stop():raise ValueError('stopped')
        with self.assertRaisesRegex(ValueError,'stopped'):device.wait_stable(stop)
        device.frame.assert_not_called()

    def test_stability_retries_one_read_timeout_without_sending_input(self):
        import subprocess
        device=self.device();clock=[0.0]
        frames=[subprocess.TimeoutExpired('screencap',3)]+[np.zeros((100,100,3),dtype=np.uint8)]*30
        device.frame=Mock(side_effect=frames)
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]),patch('android_device.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
            device.wait_stable()
        self.assertGreater(device.frame.call_count,2)
        device.command.assert_not_called()
        device.frame=Mock(side_effect=subprocess.TimeoutExpired('screencap',3))
        with patch('android_device.time.sleep'):
            with self.assertRaisesRegex(ValueError,'連續兩次'):
                device.wait_stable()
        self.assertEqual(device.frame.call_count,2)
        device.command.assert_not_called()

    def test_animation_must_settle_before_input_is_allowed(self):
        device=self.device()
        clock=[0.0]
        def frame():
            value=255 if clock[0]<3 and int(clock[0]*4)%2 else 0
            return np.full((100,100,3),value,dtype=np.uint8)
        device.frame=Mock(side_effect=frame)
        def sleep(seconds):clock[0]+=seconds
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]), patch('android_device.time.sleep',side_effect=sleep):
            elapsed=device.wait_stable()
        self.assertGreaterEqual(elapsed,3.4)
        device.command.assert_not_called()

    def test_continuous_animation_times_out_without_input(self):
        device=self.device()
        clock=[0.0]
        device.frame=Mock(side_effect=lambda:np.full((100,100,3),255*(int(clock[0]*4)%2),dtype=np.uint8))
        def sleep(seconds):clock[0]+=seconds
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]), patch('android_device.time.sleep',side_effect=sleep):
            with self.assertRaisesRegex(ValueError,'has not settled'):
                device.wait_stable(timeout=4)
        device.command.assert_not_called()

    def test_small_hand_animation_is_not_hidden_by_empty_board(self):
        device=self.device()
        clock=[0.0]
        def frame():
            pixels=np.zeros((1080,1920,3),dtype=np.uint8)
            if clock[0]<5 and int(clock[0]*4)%2:
                pixels[970:1080,850:980]=255
            return pixels
        device.frame=Mock(side_effect=frame)
        def sleep(seconds):clock[0]+=seconds
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]), patch('android_device.time.sleep',side_effect=sleep):
            self.assertGreaterEqual(device.wait_stable(),5.4)

    def test_animated_hero_skin_does_not_block_stable_cards(self):
        device=self.device()
        clock=[0.0]
        def frame():
            pixels=np.zeros((1080,1920,3),dtype=np.uint8)
            pixels[740:930,820:1080]=255*(int(clock[0]*4)%2)
            return pixels
        device.frame=Mock(side_effect=frame)
        def sleep(seconds):clock[0]+=seconds
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]), patch('android_device.time.sleep',side_effect=sleep):
            self.assertAlmostEqual(device.wait_stable(),.45,places=2)

    def test_opponent_turn_button_blocks_otherwise_stable_frame(self):
        device=self.device()
        clock=[0.0]
        def frame():
            color=(90,70,75) if clock[0]<6 else (220,180,20)
            return np.full((100,100,3),color,dtype=np.uint8)
        device.frame=Mock(side_effect=frame)
        def sleep(seconds):clock[0]+=seconds
        with patch('android_device.time.monotonic',side_effect=lambda:clock[0]), patch('android_device.time.sleep',side_effect=sleep):
            self.assertGreaterEqual(device.wait_stable(ready=lambda f:device.turn_ready(f,(.5,.5))),6.4)

    def test_enabled_green_turn_button(self):
        self.assertTrue(AndroidDevice.turn_ready(np.full((100,100,3),(60,190,30),dtype=np.uint8),(.5,.5)))

    def test_opening_animation_blocks_lit_button_until_mana_initializes(self):
        import cv2
        from android_device import _opening_zero_mana
        frame=np.full((1080,1920,3),(220,180,20),dtype=np.uint8)
        zero=_opening_zero_mana()
        frame[984:1020,1228:1302]=np.repeat(zero[:,:,None],3,axis=2)
        for size in ((1920,1080),(1280,720)):
            scaled=cv2.resize(frame,size)
            self.assertFalse(AndroidDevice.turn_ready(scaled,(.813,.455),opening=True))
            self.assertTrue(AndroidDevice.turn_ready(scaled,(.813,.455)))
        frame[984:1020,1228:1302]=(220,180,20)
        self.assertTrue(AndroidDevice.turn_ready(frame,(.813,.455),opening=True))

    def test_turn_overlay_blocks_enabled_button_at_scaled_resolution(self):
        import cv2
        from android_device import _turn_banner
        frame=np.full((1080,1920,3),(220,180,20),dtype=np.uint8)
        banner=_turn_banner()
        frame[475:575,780:1150]=np.repeat(banner[:,:,None],3,axis=2)
        for size in ((1920,1080),(1280,720)):
            self.assertFalse(AndroidDevice.turn_ready(cv2.resize(frame,size),(.813,.455)))

    def test_mulligan_confirm_requires_blue_enabled_button(self):
        for color,expected in [((10,15,20),False),((200,150,20),False),((100,190,240),True)]:
            self.assertEqual(AndroidDevice.mulligan_ready(np.full((100,100,3),color,dtype=np.uint8),(.5,.5)),expected)


if __name__ == '__main__':
    unittest.main()
