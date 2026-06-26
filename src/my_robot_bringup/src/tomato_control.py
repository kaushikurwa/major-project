#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point, Twist

class TomatoControlNode(Node):
    def __init__(self):
        super().__init__('tomato_control_node')

        self.subscription = self.create_subscription(
            Point,
            '/tomato_centroid',
            self.centroid_callback,
            10
        )
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # --- tuning parameters ---
        self.image_width  = 640      # must match camera.xacro width
        self.drive_speed  = 0.3      # forward speed m/s
        self.Kp_steer     = 0.005    # how aggressively to steer
        self.max_angular  = 0.8      # max turning speed rad/s
        self.stop_area    = 6000.0   # pixel area → robot is close enough, STOP
        self.lost_count   = 0

        # safety timer — stops robot if no message arrives
        self.last_time = self.get_clock().now()
        self.create_timer(0.1, self.safety_check)

        self.get_logger().info('Tomato Control Node started')

    def centroid_callback(self, msg: Point):
        self.last_time = self.get_clock().now()
        twist = Twist()

        # --- tomato not visible ---
        if msg.x < 0:
            self.lost_count += 1
            if self.lost_count <= 15:
                # just seen it — keep going straight briefly
                twist.linear.x  = self.drive_speed * 0.4
                twist.angular.z = 0.0
            else:
                # lost for a while — rotate slowly to search
                twist.linear.x  = 0.0
                twist.angular.z = 0.3
            self.cmd_pub.publish(twist)
            self.get_logger().warn(f'Tomato lost — lost_count={self.lost_count}')
            return

        self.lost_count = 0

        # --- check if close enough to stop ---
        area = msg.z
        if area >= self.stop_area:
            self.cmd_pub.publish(Twist())   # all zeros = full stop
            self.get_logger().info(
                f'REACHED TOMATO — area={area:.0f} >= {self.stop_area} — STOPPED'
            )
            return

        # --- steer toward tomato ---
        pixel_error = msg.x - (self.image_width / 2.0)   # + = tomato is right of center
        angular_z   = -self.Kp_steer * pixel_error        # negative = turn right
        angular_z   = max(-self.max_angular,
                      min( self.max_angular, angular_z))

        # slow down when turning sharply
        steer_ratio       = abs(angular_z) / self.max_angular
        twist.linear.x    = self.drive_speed * (1.0 - 0.5 * steer_ratio)
        twist.angular.z   = angular_z

        self.cmd_pub.publish(twist)
        self.get_logger().info(
            f'pixel_err={pixel_error:+.0f}  '
            f'angular={angular_z:+.3f}  '
            f'speed={twist.linear.x:.2f}  '
            f'area={area:.0f}'
        )

    def safety_check(self):
        elapsed = (self.get_clock().now() - self.last_time).nanoseconds / 1e9
        if elapsed > 0.5:
            self.cmd_pub.publish(Twist())   # stop if vision node dies


def main(args=None):
    rclpy.init(args=args)
    node = TomatoControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()