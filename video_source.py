import cv2
import os
import logging

class VideoFileSource:
    def __init__(self, video_path):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)

        if not self.cap.isOpened():
            raise IOError(f"Cannot open video file: {video_path}")

        # Store video properties
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps == 0:
            print("Warning: Video FPS is 0. Defaulting to 30.")
            self.fps = 30
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logging.info(f"Video source loaded: {os.path.basename(video_path)}")
        logging.info(f"Properties: {self.width}x{self.height} @ {self.fps:.2f} FPS, {self.frame_count} frames total.")

    def get_frame(self):
        """
        Reads the next frame from the video file.

        Returns:
            A tuple containing a boolean (success) and the frame (numpy array).
            Returns (False, None) at the end of the video.
        """
        ret, frame = self.cap.read()
        return ret, frame

    def get_current_frame_number(self):
        """Returns the index of the next frame to be decoded."""
        return self.cap.get(cv2.CAP_PROP_POS_FRAMES)

    def get_properties(self):
        """
        Returns the properties of the video file.
        """
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frame_count
        }

    def release(self):
        """
        Releases the video file resource.
        """
        if self.cap.isOpened():
            self.cap.release()
            logging.info(f"Video source released: {os.path.basename(self.video_path)}")

if __name__ == '__main__':
    print("Testing VideoFileSource...")

    # Create a dummy video file for testing since we can't assume one exists.
    test_video_path = "test_video.mp4"
    frame_width, frame_height = 640, 480
    fps = 30

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(test_video_path, fourcc, fps, (frame_width, frame_height))

    if not writer.isOpened():
        print("Failed to create a dummy video writer.")
    else:
        # Write 100 black frames with a frame number
        for i in range(100):
            frame = cv2.UMat(frame_height, frame_width, cv2.CV_8UC3)
            frame.setTo(0)
            text = f"Frame {i+1}"
            cv2.putText(frame, text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            writer.write(frame)
        writer.release()
        print(f"Created a dummy video file: {test_video_path}")

        # Now, test the VideoFileSource with the created file
        try:
            video_source = VideoFileSource(test_video_path)

            frame_counter = 0
            while True:
                ret, frame = video_source.get_frame()
                if not ret:
                    print("\nEnd of video reached.")
                    break

                frame_counter += 1
                # To test, we can just show a few frames
                if frame_counter <= 5 or frame_counter >= 95:
                    print(f"Read frame number: {frame_counter} (reported: {video_source.get_current_frame_number()})")
                    # cv2.imshow("Test Video", frame) # Can't show in this env
                    # cv2.waitKey(30)

            print(f"\nTotal frames read: {frame_counter}")
            video_source.release()

        except (FileNotFoundError, IOError) as e:
            print(f"Error: {e}")
        finally:
            # Clean up the dummy video file
            if os.path.exists(test_video_path):
                os.remove(test_video_path)
                print(f"Cleaned up dummy video file: {test_video_path}")

    print("\nVideoFileSource test finished.")
