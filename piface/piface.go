package main

import (
	"container/ring"
	"fmt"
	"image"
	"image/color"
	"log"
	"os"
	"time"

	"gocv.io/x/gocv"
)

// FindFaces uses a classifier to identify faces
func FindFaces(c gocv.CascadeClassifier, img gocv.Mat, imgs chan gocv.Mat, events chan DetectionEvent) {
	// color for the rect when faces detected
	blue := color.RGBA{0, 0, 255, 0}

	for i := range imgs {
		rects := c.DetectMultiScale(i)

		events <- DetectionEvent{Rects: rects, Time: time.Now(), Img: i}

		// draw a rectangle around each face on the original image,
		// along with text identifing as "Human"
		for _, r := range rects {
			//fmt.Printf("%T: %+v\n", r, r)
			gocv.Rectangle(&img, r, blue, 3)

			size := gocv.GetTextSize("Human", gocv.FontHersheyPlain, 1.2, 2)
			pt := image.Pt(r.Min.X+(r.Min.X/2)-(size.X/2), r.Min.Y-2)
			gocv.PutText(&img, "Human", pt, gocv.FontHersheyPlain, 1.2, blue, 2)
		}
	}
}

// ReadImages reads images from a video device and sends them to a channel for processing
func ReadImages(webcam *gocv.VideoCapture, img gocv.Mat, imgs chan gocv.Mat, window *gocv.Window) {
	// loop
	for {
		if ok := webcam.Read(&img); !ok {
			log.Printf("Device closed")
			return
		}
		if img.Empty() {
			continue
		}
		imgs <- img

		window.IMShow(img)
		if window.WaitKey(1) >= 0 {
			break
		}
	}
}

// SaveVideos saves videos if interesting events are detected
func SaveVideos(events chan DetectionEvent) {
	//var err error
	var slidingWindow []DetectionEvent
	buf := ring.New(60)
	frames := make(chan gocv.Mat)
	i := 0
	var writer bool

	for e := range events {
		log.Printf("found %d faces", len(e.Rects))
		slidingWindow = append(slidingWindow, e)

		buf.Value, _ = e.Img.ToImage()
		buf = buf.Next()
		i++

		if len(e.Rects) > 0 {
			if !writer {
				// start the writer
				go func(frames chan gocv.Mat) {
					writer = true
					f := NewVideoFilename()
					w, err := NewVideoWriter(f, e.Img)
					if err != nil {
						fmt.Printf("error: %v\n", err)
						return
					}
					log.Printf("new video file: %s", f)
					for i := range frames {
						w.Write(i)
					}
					w.Close()
					os.Exit(0)
				}(frames)

				buf.Do(func(p interface{}) {
					defer func() {
						if r := recover(); r != nil {
							return
						}
					}()

					d := p.(image.Image)
					m, err := gocv.ImageToMatRGB(d)
					if err != nil {
						return
					}
					frames <- m
				})
			}
			frames <- e.Img
		} else {
			if writer {
				close(frames)
				log.Println("Exiting!")
				return
			}
		}

		/*
			if i == buf.Len() {
				f := NewVideoFilename()
				w, err := NewVideoWriter(f, e.Img)
				if err != nil {
					fmt.Printf("error: %v\n", err)
					return
				}

				log.Printf("new video file: %s", f)
				buf.Do(func(p interface{}) {
					d := p.(image.Image)
					m, err := gocv.ImageToMatRGB(d)
					if err != nil {
						return
					}
					w.Write(m)
				})
				w.Close()
				os.Exit(0)
			}
		*/

		/*
			record 5 seconds before
			record 5 seconds after
		*/

		// logic:
		//
		// clip continuing
		//  - write images
		// clip ending
		//  - write images
		//  - end clip
		// new clip?
		//  - create new clip
		//  - send buffer of images
		/*
		 */
	}
}

// DetectionEvent represents a detection of an object in a video stream
type DetectionEvent struct {
	Rects []image.Rectangle
	Time  time.Time
	Img   gocv.Mat
}

// NewVideoFilename returns a new filename for writing video files to
func NewVideoFilename() string {
	t := time.Now()
	return fmt.Sprintf("%d-%02d-%02dT%02d:%02d:%02d.mp4", t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), t.Second())
}

// NewVideoWriter produces a new file a video can be written to
func NewVideoWriter(fn string, img gocv.Mat) (*gocv.VideoWriter, error) {
	writer, err := gocv.VideoWriterFile(fn, "avc1", 25, img.Cols(), img.Rows(), true)
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
	deviceID := 0
	xmlFile := "data/haarcascade_frontalface_default.xml"

	//deviceID := "data/sample-mp4-file.mp4"
	//deviceID := "https://cams.cdn-surfline.com/cdn-au/au-umina/chunklist.m3u8"
	//xmlFile := "data/haarcascade_upperbody.xml"

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

	// load classifier to recognize faces
	classifier := gocv.NewCascadeClassifier()
	defer classifier.Close()

	if !classifier.Load(xmlFile) {
		fmt.Printf("Error reading cascade file: %v\n", xmlFile)
		return
	}

	// set up stream
	imgs := make(chan gocv.Mat)
	events := make(chan DetectionEvent)

	go SaveVideos(events)
	go FindFaces(classifier, img, imgs, events)
	ReadImages(webcam, img, imgs, window)
}
