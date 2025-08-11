import cv2
import config

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.cap.isOpened():
            raise IOError(f"Cannot open camera at index {config.CAMERA_INDEX}")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.DESIRED_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.DESIRED_HEIGHT)

        self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camera initialized with resolution: {self.actual_width}x{self.actual_height}")

    def get_frame(self):
        """
        Reads a frame from the camera.

        Returns:
            A tuple containing a boolean (success) and the frame (numpy array).
        """
        ret, frame = self.cap.read()
        return ret, frame

    def release(self):
        """
        Releases the camera resource.
        """
        if self.cap.isOpened():
            self.cap.release()
            print("Camera released.")

    def get_properties(self):
        """
        Returns the actual properties of the camera feed.
        """
        return {
            "width": self.actual_width,
            "height": self.actual_height,
            "fps": self.cap.get(cv2.CAP_PROP_FPS) or config.FPS
        }

if __name__ == '__main__':
    # Example usage for testing the camera module
    try:
        camera = Camera()
        print("Camera properties:", camera.get_properties())

        while True:
            ret, frame = camera.get_frame()
            if not ret:
                print("Failed to grab frame")
                break

            cv2.imshow('Camera Test', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except IOError as e:
        print(e)
    finally:
        if 'camera' in locals() and camera:
            camera.release()
        cv2.destroyAllWindows()
        print("Test finished.")
