package org.example;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;
import java.io.StringReader;

public class StateCount {

    public static class StateMapper
            extends Mapper<LongWritable, Text, Text, LongWritable> {

        private final Text outKey = new Text();
        private final LongWritable outValue = new LongWritable(1);

        @Override
        protected void map(LongWritable key,
                           Text value,
                           Context context)
                throws IOException, InterruptedException {

            String line = value.toString();

            // 跳过表头
            if (line.startsWith("Date received,")) {
                return;
            }

            try (CSVParser parser = CSVParser.parse(
                    new StringReader(line),
                    CSVFormat.DEFAULT)) {

                for (CSVRecord record : parser) {
                    if (record.size() < 8) {
                        context.getCounter("StateCount", "INVALID_CSV").increment(1);
                        return;
                    }

                    // 提取第7列 State
                    String state = record.get(7).trim();

                    // 空值跳过
                    if (state.isEmpty()) {
                        context.getCounter("StateCount", "EMPTY_STATE").increment(1);
                        return;
                    }

                    outKey.set(state);
                    context.write(outKey, outValue);
                }

            } catch (Exception e) {
                context.getCounter("StateCount", "PARSE_ERROR").increment(1);
            }
        }
    }

    public static class StateReducer
            extends Reducer<Text, LongWritable, Text, LongWritable> {

        private final LongWritable result = new LongWritable();

        @Override
        protected void reduce(Text key,
                              Iterable<LongWritable> values,
                              Context context)
                throws IOException, InterruptedException {

            long sum = 0;
            for (LongWritable value : values) {
                sum += value.get();
            }

            result.set(sum);
            context.write(key, result);
        }
    }

    public static void main(String[] args) throws Exception {

        if (args.length != 2) {
            System.err.println("用法：StateCount <输入路径> <输出路径>");
            System.exit(2);
        }

        Configuration conf = new Configuration();

        Job job = Job.getInstance(conf, "CFPB State Complaint Count");
        job.setJarByClass(StateCount.class);

        job.setMapperClass(StateMapper.class);
        job.setCombinerClass(StateReducer.class);
        job.setReducerClass(StateReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);

        job.setNumReduceTasks(1);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
