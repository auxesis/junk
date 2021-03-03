// What it does:
//
// This example uses the CascadeClassifier class to detect faces,
// and draw a rectangle around each of them, before displaying them within a Window.
//
// How to run:
//
// facedetect [camera ID] [classifier XML file]
//
// 		go run ./cmd/facedetect/main.go 0 data/haarcascade_frontalface_default.xml
//
// +build example

package main

import (
	"fmt"
	"image"
	"image/color"
	"log"
	"os"
	"time"

	"gocv.io/x/gocv"
)

// NewVideoFilename returns a new filename for writing video files to
func NewVideoFilename() string {
	t := time.Now()
	return fmt.Sprintf("%d-%02d-%02dT%02d:%02d:%02d.mp4", t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), t.Second())
}

// NewVideoWriter produces a new file a video can be written to
func NewVideoWriter(fn string, img gocv.Mat) (*gocv.VideoWriter, error) {
	writer, err := gocv.VideoWriterFile(fn, "avc1", 8, img.Cols(), img.Rows(), true)
	if err != nil {
		return writer, fmt.Errorf("error opening video writer device: %v :: %w", fn, err)
	}
	return writer, err
}

// NoBig returns if there are any big rectangles in a slice
func NoBig(rects []image.Rectangle) bool {
	for _, r := range rects {
		s := r.Size()
		if s.X >= 200 || s.Y >= 200 {
			return false
		}
	}
	return true
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage:\n\tfacedetect [camera ID] [classifier XML file]")
		return
	}

	// parse args
	deviceID := os.Args[1]
	xmlFile := os.Args[2]

	// open webcam
	webcam, err := gocv.OpenVideoCapture(deviceID)
	if err != nil {
		fmt.Printf("error opening video capture device: %v\n", deviceID)
		return
	}
	defer webcam.Close()

	// open display window
	window := gocv.NewWindow("Face Detect")
	defer window.Close()

	// prepare image matrix
	img := gocv.NewMat()
	defer img.Close()

	// color for the rect when faces detected
	blue := color.RGBA{0, 0, 255, 0}

	// load classifier to recognize faces
	classifier := gocv.NewCascadeClassifier()
	defer classifier.Close()

	if !classifier.Load(xmlFile) {
		fmt.Printf("Error reading cascade file: %v\n", xmlFile)
		return
	}

	var writer *gocv.VideoWriter
	fmt.Printf("Start reading device: %v\n", deviceID)
	for {
		if ok := webcam.Read(&img); !ok {
			fmt.Printf("Device closed: %v\n", deviceID)
			return
		}
		if img.Empty() {
			continue
		}

		// detect faces
		rects := classifier.DetectMultiScale(img)
		//log.Printf("found %d faces\n", len(rects))

		// draw a rectangle around each face on the original image,
		// along with text identifing as "Human"
		for _, r := range rects {
			//fmt.Printf("%T: %+v\n", r, r)
			gocv.Rectangle(&img, r, blue, 3)

			size := gocv.GetTextSize("Human", gocv.FontHersheyPlain, 1.2, 2)
			pt := image.Pt(r.Min.X+(r.Min.X/2)-(size.X/2), r.Min.Y-2)
			gocv.PutText(&img, "Human", pt, gocv.FontHersheyPlain, 1.2, blue, 2)
		}

		if len(rects) > 0 {
			if writer == nil {
				log.Printf("img: %T %+v %T %+v %+v\n", img, img, rects[0], rects[0], rects[0].Size())
				if NoBig(rects) {
					continue
				}
				f := NewVideoFilename()
				writer, err = NewVideoWriter(f, img)
				if err != nil {
					fmt.Printf("error: %v\n", err)
					return
				}
				defer writer.Close()
				log.Printf("new video file: %s", f)
				log.Printf("found %d faces", len(rects))
			}
			writer.Write(img)
		} else if writer != nil {
			writer.Close()
			writer = nil
		}

		// show the image in the window, and wait 1 millisecond
		window.IMShow(img)
		if window.WaitKey(1) >= 0 {
			break
		}
	}
}
