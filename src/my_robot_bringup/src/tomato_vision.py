#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from cv_bridge import CvBridge
import cv2
import numpy as np

class TomatoVisionNode(Node):
    def __init__(self):
        super().__init__('tomato_vision_node')
        self.subscription = self.create_subscription(
            Image,
            '/camera/image_raw',        # your camera topic
            self.image_callback,
            10
        )
        self.centroid_pub = self.create_publisher(Point, '/tomato_centroid', 10)
        self.bridge = CvBridge()
        self.get_logger().info('Tomato Vision Node started — looking for RED CIRCLE')

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        h, w = frame.shape[:2]

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Red wraps around in HSV so needs two ranges
        lower_red1 = np.array([0,   100,  50])
        upper_red1 = np.array([10,  255, 255])
        lower_red2 = np.array([160, 100,  50])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        # Remove noise
        kernel = np.ones((5, 5), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN,  kernel)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(
            red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        best     = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 200:              # ignore tiny blobs
                continue

            # Circularity = 4*pi*area / perimeter^2  →  1.0 = perfect circle
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter ** 2)

            if circularity > 0.7:       # tomato is roughly circular
                if area > best_area:
                    best_area = area
                    best = cnt

        pt = Point()

        if best is not None:
            (cx, cy), radius = cv2.minEnclosingCircle(best)
            cx, cy = int(cx), int(cy)

            pt.x = float(cx)
            pt.y = float(cy)
            pt.z = float(best_area)     # area used by control node to know distance

            self.get_logger().info(
                f'TOMATO found → centroid=({cx},{cy})  '
                f'radius={radius:.1f}px  area={best_area:.0f}'
            )

            # Draw on frame
            cv2.circle(frame, (cx, cy), int(radius), (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
            cv2.putText(frame, f'TOMATO r={radius:.0f}px',
                        (cx - 40, cy - int(radius) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        else:
            pt.x = -1.0
            pt.y = -1.0
            pt.z =  0.0
            self.get_logger().warn('No tomato in frame')

        self.centroid_pub.publish(pt)

        # Center line reference
        cv2.line(frame, (w//2, 0), (w//2, h), (255, 255, 0), 1)
        cv2.imshow('Camera Feed', frame)
        cv2.imshow('Red Mask',    red_mask)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    node = TomatoVisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()